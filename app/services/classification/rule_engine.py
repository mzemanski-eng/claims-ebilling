"""
Rule-based classification engine.

Evaluation order (highest to lowest specificity):
  1. EXACT_CODE   — raw_code matches a MappingRule.match_pattern exactly
  2. REGEX_PATTERN — raw_description matches a compiled regex
  3. KEYWORD_SET  — all keywords in match_pattern found in raw_description
  4. Built-in heuristics (component detection for travel/mileage)
  5. UNRECOGNIZED — no match found

Design for ML upgrade:
  This module exposes a classify() function that takes a raw description/code
  and returns a ClassificationResult. When ML is added in v2, the caller
  (classifier.py) can try ML first and fall back to rules, or blend scores —
  without changing any downstream code.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass
class ClassificationResult:
    taxonomy_code: Optional[str]
    billing_component: Optional[str]
    confidence: str  # HIGH | MEDIUM | LOW | UNRECOGNIZED
    confidence_weight: float  # 0.0–1.0
    match_type: Optional[
        str
    ]  # exact_code | regex_pattern | keyword_set | heuristic | None
    matched_rule_id: Optional[
        str
    ]  # MappingRule.id if DB-backed; None for built-in heuristics
    match_explanation: str  # Human-readable explanation for audit


# ── Built-in keyword rules (bootstrap rules; carrier adds/overrides via DB) ──
# Format: (match_type, match_pattern, taxonomy_code, billing_component, weight)
# These are fallback rules only — DB-backed MappingRules always take precedence.

BUILTIN_RULES: list[tuple[str, str, str, str, float]] = [
    # ── ENG ──────────────────────────────────────────────────────────────────
    ("keyword_set", "cause,origin", "ENG.CAO.L2", "L2", 0.90),
    (
        "regex_pattern",
        r"cause\s+(&|and)\s+origin",
        "ENG.CAO.L2",
        "L2",
        0.92,
    ),
    ("keyword_set", "fire,origin", "ENG.FOC.L2", "L2", 0.90),
    (
        "regex_pattern",
        r"fire\s+origin",
        "ENG.FOC.L2",
        "L2",
        0.90,
    ),
    ("keyword_set", "failure,analysis", "ENG.FA.L2", "L2", 0.88),
    ("keyword_set", "damage,assessment,engineer", "ENG.DA.L2", "L2", 0.82),
    (
        "keyword_set",
        "expert,witness,engineer",
        "ENG.EWD.L2",
        "L2",
        0.85,
    ),
    (
        "keyword_set",
        "testimony,deposition,engineer",
        "ENG.EWD.L2",
        "L2",
        0.88,
    ),
    ("keyword_set", "peer review,engineer", "ENG.PR.L2", "L2", 0.85),
    ("keyword_set", "engineering,analysis", "ENG.EA.L2", "L2", 0.80),
    # ── IA ───────────────────────────────────────────────────────────────────
    ("keyword_set", "field,adjust", "IA.FIELD_ASSIGN.PROF_FEE", "PROF_FEE", 0.82),
    (
        "keyword_set",
        "field adjusting,daily rate",
        "IA.FIELD_ASSIGN.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "desk,assignment,adjust",
        "IA.DESK_ASSIGN.PROF_FEE",
        "PROF_FEE",
        0.82,
    ),
    ("keyword_set", "desk assignment", "IA.DESK_ASSIGN.PROF_FEE", "PROF_FEE", 0.82),
    ("keyword_set", "desk,adjust", "IA.DESK_ASSIGN.PROF_FEE", "PROF_FEE", 0.80),
    (
        "keyword_set",
        "catastrophe,assignment",
        "IA.CAT_ASSIGN.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    (
        "regex_pattern",
        r"\bcat\s+(assign|deployment|daily)\b",
        "IA.CAT_ASSIGN.PROF_FEE",
        "PROF_FEE",
        0.85,
    ),
    ("keyword_set", "photo,documentation", "IA.PHOTO_DOC.PROF_FEE", "PROF_FEE", 0.88),
    (
        "keyword_set",
        "supplement,handling",
        "IA.SUPPLEMENT_HANDLING.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    ("keyword_set", "file,open,fee", "IA.ADMIN.FILE_OPEN_FEE", "FILE_OPEN_FEE", 0.90),
    # ── REC ──────────────────────────────────────────────────────────────────
    (
        "keyword_set",
        "medical,records,retrieval",
        "REC.MED_RECORDS.RETRIEVAL_FEE",
        "RETRIEVAL_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "medical records,request",
        "REC.MED_RECORDS.RETRIEVAL_FEE",
        "RETRIEVAL_FEE",
        0.85,
    ),
    (
        "keyword_set",
        "copy,per page,records",
        "REC.MED_RECORDS.COPY_REPRO",
        "COPY_REPRO",
        0.82,
    ),
    (
        "keyword_set",
        "rush,records",
        "REC.MED_RECORDS.RUSH_PREMIUM",
        "RUSH_PREMIUM",
        0.85,
    ),
    (
        "keyword_set",
        "certified,copy",
        "REC.MED_RECORDS.CERT_COPY_FEE",
        "CERT_COPY_FEE",
        0.85,
    ),
    (
        "keyword_set",
        "employment,records",
        "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE",
        "RETRIEVAL_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "court,records",
        "REC.LEGAL_RECORDS.RETRIEVAL_FEE",
        "RETRIEVAL_FEE",
        0.85,
    ),
    (
        "keyword_set",
        "police,report",
        "REC.LEGAL_RECORDS.RETRIEVAL_FEE",
        "RETRIEVAL_FEE",
        0.82,
    ),
    # ── LA ───────────────────────────────────────────────────────────────────
    ("keyword_set", "ladder,assist", "LA.LADDER_ACCESS.FLAT_FEE", "FLAT_FEE", 0.92),
    ("keyword_set", "ladder,access", "LA.LADDER_ACCESS.FLAT_FEE", "FLAT_FEE", 0.92),
    (
        "keyword_set",
        "roof,inspect,harness",
        "LA.ROOF_INSPECT_HARNESS.FLAT_FEE",
        "FLAT_FEE",
        0.90,
    ),
    ("keyword_set", "roof,inspect", "LA.ROOF_INSPECT.FLAT_FEE", "FLAT_FEE", 0.85),
    ("keyword_set", "tarp,cover", "LA.TARP_COVER.FLAT_FEE", "FLAT_FEE", 0.90),
    ("regex_pattern", r"\btarp\b", "LA.TARP_COVER.FLAT_FEE", "FLAT_FEE", 0.85),
    # ── INSP ─────────────────────────────────────────────────────────────────
    ("keyword_set", "property,inspection", "INSP.BASIC.FLAT_FEE", "FLAT_FEE", 0.80),
    (
        "keyword_set",
        "re-inspection,disputed",
        "INSP.DISPUTE_REINSPECT.FLAT_FEE",
        "FLAT_FEE",
        0.88,
    ),
    ("keyword_set", "re-inspection", "INSP.REINSPECT.FLAT_FEE", "FLAT_FEE", 0.82),
    ("keyword_set", "exterior,inspection", "INSP.EXTERIOR.FLAT_FEE", "FLAT_FEE", 0.85),
    (
        "keyword_set",
        "drive-by,inspection",
        "INSP.EXTERIOR.FLAT_FEE",
        "FLAT_FEE",
        0.85,
    ),
    ("keyword_set", "interior,inspection", "INSP.INTERIOR.FLAT_FEE", "FLAT_FEE", 0.85),
    (
        "keyword_set",
        "supplement,review",
        "INSP.SUPPLEMENT_REVIEW.FLAT_FEE",
        "FLAT_FEE",
        0.85,
    ),
    (
        "keyword_set",
        "damage,assessment,report",
        "INSP.DAMAGE_ASSESS.FLAT_FEE",
        "FLAT_FEE",
        0.85,
    ),
    # ── VIRT ─────────────────────────────────────────────────────────────────
    ("keyword_set", "virtual,inspection", "VIRT.GUIDED.FLAT_FEE", "FLAT_FEE", 0.88),
    ("keyword_set", "guided,virtual", "VIRT.GUIDED.FLAT_FEE", "FLAT_FEE", 0.90),
    (
        "keyword_set",
        "self-service,video,inspection",
        "VIRT.SELF_SERVICE.FLAT_FEE",
        "FLAT_FEE",
        0.88,
    ),
    ("keyword_set", "ai,scope", "VIRT.AI_SCOPE.FLAT_FEE", "FLAT_FEE", 0.85),
    (
        "keyword_set",
        "aerial,analysis",
        "VIRT.AERIAL_ANALYSIS.FLAT_FEE",
        "FLAT_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "satellite,image",
        "VIRT.AERIAL_ANALYSIS.FLAT_FEE",
        "FLAT_FEE",
        0.85,
    ),
    (
        "regex_pattern",
        r"\b(eagleview|nearmap|verisk)\b",
        "VIRT.AERIAL_ANALYSIS.FLAT_FEE",
        "FLAT_FEE",
        0.90,
    ),
    ("keyword_set", "photo,ai,damage", "VIRT.PHOTO_AI.FLAT_FEE", "FLAT_FEE", 0.85),
    # ── CR — Court Reporting ──────────────────────────────────────────────────
    (
        "keyword_set",
        "court,reporter,appearance",
        "CR.DEPO.APPEARANCE_FEE",
        "APPEARANCE_FEE",
        0.92,
    ),
    (
        "keyword_set",
        "deposition,transcript",
        "CR.DEPO.TRANSCRIPT",
        "TRANSCRIPT",
        0.92,
    ),
    (
        "regex_pattern",
        r"\bdepo(sition)?\s+transcript\b",
        "CR.DEPO.TRANSCRIPT",
        "TRANSCRIPT",
        0.92,
    ),
    ("keyword_set", "transcript,copy", "CR.DEPO.COPY_FEE", "COPY_FEE", 0.85),
    ("keyword_set", "deposition,video", "CR.DEPO.VIDEOGRAPHY", "VIDEOGRAPHY", 0.90),
    (
        "keyword_set",
        "rush,transcript",
        "CR.DEPO.RUSH_TRANSCRIPT",
        "RUSH_TRANSCRIPT",
        0.90,
    ),
    (
        "keyword_set",
        "exhibit,handling",
        "CR.DEPO.EXHIBIT_HANDLING",
        "EXHIBIT_HANDLING",
        0.88,
    ),
    (
        "keyword_set",
        "remote,deposition,technology",
        "CR.DEPO.REMOTE_FEE",
        "REMOTE_FEE",
        0.88,
    ),
    (
        "regex_pattern",
        r"\b(zoom|teams|veritext)\b.*depo",
        "CR.DEPO.REMOTE_FEE",
        "REMOTE_FEE",
        0.85,
    ),
    # ── INV ──────────────────────────────────────────────────────────────────
    ("keyword_set", "surveillance", "INV.SURVEILLANCE.PROF_FEE", "PROF_FEE", 0.92),
    ("keyword_set", "recorded,statement", "INV.STATEMENT.PROF_FEE", "PROF_FEE", 0.90),
    (
        "keyword_set",
        "background,asset",
        "INV.BACKGROUND_ASSET.PROF_FEE",
        "PROF_FEE",
        0.85,
    ),
    ("keyword_set", "aoe,coe", "INV.AOE_COE.PROF_FEE", "PROF_FEE", 0.92),
    ("regex_pattern", r"aoe\s*/?\s*coe", "INV.AOE_COE.PROF_FEE", "PROF_FEE", 0.92),
    ("keyword_set", "skip,trace", "INV.SKIP_TRACE.PROF_FEE", "PROF_FEE", 0.92),
    # ── DRNE ─────────────────────────────────────────────────────────────────
    ("keyword_set", "drone,roof", "DRNE.ROOF_SURVEY.FLAT_FEE", "FLAT_FEE", 0.92),
    ("keyword_set", "drone,survey", "DRNE.ROOF_SURVEY.FLAT_FEE", "FLAT_FEE", 0.88),
    ("keyword_set", "aerial,photo", "DRNE.AERIAL_PHOTO.FLAT_FEE", "FLAT_FEE", 0.85),
    ("keyword_set", "drone,video", "DRNE.VIDEO.FLAT_FEE", "FLAT_FEE", 0.88),
    ("keyword_set", "thermal,imaging", "DRNE.THERMAL.FLAT_FEE", "FLAT_FEE", 0.90),
    ("keyword_set", "infrared,survey", "DRNE.THERMAL.FLAT_FEE", "FLAT_FEE", 0.88),
    # ── APPR ─────────────────────────────────────────────────────────────────
    (
        "keyword_set",
        "property,appraisal",
        "APPR.PROPERTY_APPRAISAL.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    ("keyword_set", "umpire,services", "APPR.UMPIRE.PROF_FEE", "PROF_FEE", 0.92),
    ("regex_pattern", r"\bumpire\b", "APPR.UMPIRE.PROF_FEE", "PROF_FEE", 0.88),
    (
        "keyword_set",
        "contents,inventory",
        "APPR.CONTENTS_INVENTORY.PROF_FEE",
        "PROF_FEE",
        0.90,
    ),
    (
        "keyword_set",
        "contents,valuation",
        "APPR.CONTENTS_INVENTORY.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "appraisal,site,visit",
        "APPR.SITE_VISIT.FLAT_FEE",
        "FLAT_FEE",
        0.88,
    ),
    # ── Shared generic heuristics (low weight — domain rules above take priority) ─
    # Generic no-show / cancellation fallback when no domain context is available.
    ("keyword_set", "no.show,fee", "CR.NO_SHOW.NO_SHOW_FEE", "NO_SHOW_FEE", 0.70),
    ("regex_pattern", r"no.?show", "CR.NO_SHOW.NO_SHOW_FEE", "NO_SHOW_FEE", 0.68),
    (
        "keyword_set",
        "cancellation,fee",
        "XDOMAIN.ADMIN_MISC.ADMIN_FEE",
        "ADMIN_FEE",
        0.50,
    ),
    ("regex_pattern", r"\bcancel", "XDOMAIN.ADMIN_MISC.ADMIN_FEE", "ADMIN_FEE", 0.45),
    # Generic travel fallbacks — point to IA (most common travel domain).
    ("regex_pattern", r"\bmileage\b", "IA.FIELD_ASSIGN.MILEAGE", "MILEAGE", 0.55),
    ("regex_pattern", r"\bmiles?\b", "IA.FIELD_ASSIGN.MILEAGE", "MILEAGE", 0.50),
    (
        "keyword_set",
        "airfare",
        "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT",
        "TRAVEL_TRANSPORT",
        0.55,
    ),
    (
        "keyword_set",
        "lodging",
        "IA.FIELD_ASSIGN.TRAVEL_LODGING",
        "TRAVEL_LODGING",
        0.55,
    ),
    ("keyword_set", "hotel", "IA.FIELD_ASSIGN.TRAVEL_LODGING", "TRAVEL_LODGING", 0.52),
    (
        "keyword_set",
        "meals,per diem",
        "IA.FIELD_ASSIGN.TRAVEL_MEALS",
        "TRAVEL_MEALS",
        0.55,
    ),
    (
        "keyword_set",
        "pass.through",
        "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST",
        "THIRD_PARTY_COST",
        0.70,
    ),
]

# ── Compiled rule cache ───────────────────────────────────────────────────────
_COMPILED_RULES: list[tuple] | None = None


def _compile_rules() -> list[tuple]:
    """Compile all regex patterns once at startup."""
    compiled = []
    for match_type, pattern, taxonomy_code, billing_component, weight in BUILTIN_RULES:
        if match_type == "regex_pattern":
            try:
                rx = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                logger.warning("Invalid regex in BUILTIN_RULES: %r — %s", pattern, e)
                continue
            compiled.append(
                (match_type, pattern, rx, taxonomy_code, billing_component, weight)
            )
        elif match_type == "keyword_set":
            keywords = [k.strip().lower() for k in re.split(r"[,|]", pattern)]
            compiled.append(
                (
                    match_type,
                    pattern,
                    keywords,
                    taxonomy_code,
                    billing_component,
                    weight,
                )
            )
        else:
            compiled.append(
                (match_type, pattern, None, taxonomy_code, billing_component, weight)
            )
    return compiled


def get_compiled_rules() -> list[tuple]:
    global _COMPILED_RULES
    if _COMPILED_RULES is None:
        _COMPILED_RULES = _compile_rules()
    return _COMPILED_RULES


# ── Core classify function ────────────────────────────────────────────────────


def classify_with_builtin_rules(
    raw_description: str,
    raw_code: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify a raw line item using built-in rules only (no DB lookup).
    Used as the fallback when no DB MappingRule matches.

    Returns UNRECOGNIZED if nothing matches.
    """
    desc_lower = raw_description.lower().strip()
    # raw_code is available for future code-based matching rules; unused in v1

    best: Optional[tuple] = (
        None  # (weight, taxonomy_code, billing_component, match_type, pattern, explanation)
    )

    for rule in get_compiled_rules():
        match_type = rule[0]
        pattern_str = rule[1]
        compiled = rule[2]
        taxonomy_code = rule[3]
        billing_component = rule[4]
        weight = rule[5]

        if match_type == "keyword_set":
            keywords: list[str] = compiled
            # Allow comma, space, or dot as separator within multi-word keywords
            if all(
                kw in desc_lower or kw.replace(".", "").replace("-", "") in desc_lower
                for kw in keywords
            ):
                if best is None or weight > best[0]:
                    best = (
                        weight,
                        taxonomy_code,
                        billing_component,
                        match_type,
                        pattern_str,
                        f"Keyword match: {pattern_str!r}",
                    )

        elif match_type == "regex_pattern":
            rx = compiled
            if rx.search(desc_lower):
                if best is None or weight > best[0]:
                    best = (
                        weight,
                        taxonomy_code,
                        billing_component,
                        match_type,
                        pattern_str,
                        f"Regex match: {pattern_str!r}",
                    )

    if best is None:
        return ClassificationResult(
            taxonomy_code=None,
            billing_component=None,
            confidence="UNRECOGNIZED",
            confidence_weight=0.0,
            match_type=None,
            matched_rule_id=None,
            match_explanation=f"No rule matched description: {raw_description!r}",
        )

    weight, taxonomy_code, billing_component, match_type, pattern_str, explanation = (
        best
    )

    # Map weight to confidence label
    if weight >= 0.85:
        confidence = "HIGH"
    elif weight >= 0.65:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return ClassificationResult(
        taxonomy_code=taxonomy_code,
        billing_component=billing_component,
        confidence=confidence,
        confidence_weight=weight,
        match_type=match_type,
        matched_rule_id=None,  # Built-in rules have no DB ID
        match_explanation=explanation,
    )
