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
    # ── IME ──────────────────────────────────────────────────────────────────
    ("keyword_set", "ime,physician,exam", "IME.PHY_EXAM.PROF_FEE", "PROF_FEE", 0.75),
    (
        "keyword_set",
        "independent medical examination",
        "IME.PHY_EXAM.PROF_FEE",
        "PROF_FEE",
        0.80,
    ),
    ("keyword_set", "ime,examination", "IME.PHY_EXAM.PROF_FEE", "PROF_FEE", 0.72),
    ("regex_pattern", r"\bime\b.*\bexam", "IME.PHY_EXAM.PROF_FEE", "PROF_FEE", 0.78),
    (
        "regex_pattern",
        r"\bindependent medical\b",
        "IME.PHY_EXAM.PROF_FEE",
        "PROF_FEE",
        0.80,
    ),
    (
        "keyword_set",
        "multi.specialty,panel,ime",
        "IME.MULTI_SPECIALTY.PROF_FEE",
        "PROF_FEE",
        0.80,
    ),
    (
        "keyword_set",
        "multi-specialty,ime",
        "IME.MULTI_SPECIALTY.PROF_FEE",
        "PROF_FEE",
        0.80,
    ),
    (
        "keyword_set",
        "records review,no exam",
        "IME.RECORDS_REVIEW.PROF_FEE",
        "PROF_FEE",
        0.85,
    ),
    (
        "keyword_set",
        "file review,no exam",
        "IME.RECORDS_REVIEW.PROF_FEE",
        "PROF_FEE",
        0.82,
    ),
    (
        "regex_pattern",
        r"records?\s+review.*no.?exam",
        "IME.RECORDS_REVIEW.PROF_FEE",
        "PROF_FEE",
        0.85,
    ),
    ("keyword_set", "addendum,report", "IME.ADDENDUM.PROF_FEE", "PROF_FEE", 0.85),
    ("regex_pattern", r"\baddendum\b", "IME.ADDENDUM.PROF_FEE", "PROF_FEE", 0.82),
    ("keyword_set", "peer review", "IME.PEER_REVIEW.PROF_FEE", "PROF_FEE", 0.88),
    (
        "regex_pattern",
        r"\bpeer.?review\b",
        "IME.PEER_REVIEW.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "cancellation,fee",
        "IME.CANCELLATION.CANCEL_FEE",
        "CANCEL_FEE",
        0.90,
    ),
    ("regex_pattern", r"\bcancel", "IME.CANCELLATION.CANCEL_FEE", "CANCEL_FEE", 0.85),
    ("keyword_set", "no.show,fee", "IME.NO_SHOW.NO_SHOW_FEE", "NO_SHOW_FEE", 0.92),
    ("regex_pattern", r"no.?show", "IME.NO_SHOW.NO_SHOW_FEE", "NO_SHOW_FEE", 0.90),
    (
        "keyword_set",
        "scheduling,fee",
        "IME.ADMIN.SCHEDULING_FEE",
        "SCHEDULING_FEE",
        0.80,
    ),
    (
        "keyword_set",
        "admin,scheduling",
        "IME.ADMIN.SCHEDULING_FEE",
        "SCHEDULING_FEE",
        0.78,
    ),
    # ── ENG ──────────────────────────────────────────────────────────────────
    (
        "keyword_set",
        "property,inspection,engineer",
        "ENG.PROPERTY_INSPECT.PROF_FEE",
        "PROF_FEE",
        0.82,
    ),
    ("keyword_set", "cause,origin", "ENG.CAUSE_ORIGIN.PROF_FEE", "PROF_FEE", 0.90),
    (
        "regex_pattern",
        r"cause\s+(&|and)\s+origin",
        "ENG.CAUSE_ORIGIN.PROF_FEE",
        "PROF_FEE",
        0.92,
    ),
    (
        "keyword_set",
        "structural,assessment",
        "ENG.STRUCTURAL_ASSESS.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "expert,report,engineer",
        "ENG.EXPERT_REPORT.PROF_FEE",
        "PROF_FEE",
        0.80,
    ),
    (
        "keyword_set",
        "testimony,deposition",
        "ENG.TESTIMONY_DEPO.PROF_FEE",
        "PROF_FEE",
        0.88,
    ),
    (
        "keyword_set",
        "supplemental,inspection",
        "ENG.SUPPLEMENTAL_INSPECT.PROF_FEE",
        "PROF_FEE",
        0.82,
    ),
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
    # ── XDOMAIN travel/mileage heuristics (apply across domains) ─────────────
    # These are intentionally lower weight — domain-specific rules take priority
    ("regex_pattern", r"\bmileage\b", "IME.PHY_EXAM.MILEAGE", "MILEAGE", 0.60),
    ("regex_pattern", r"\bmiles?\b", "IME.PHY_EXAM.MILEAGE", "MILEAGE", 0.55),
    (
        "keyword_set",
        "airfare",
        "IME.PHY_EXAM.TRAVEL_TRANSPORT",
        "TRAVEL_TRANSPORT",
        0.65,
    ),
    ("keyword_set", "lodging", "IME.PHY_EXAM.TRAVEL_LODGING", "TRAVEL_LODGING", 0.60),
    ("keyword_set", "hotel", "IME.PHY_EXAM.TRAVEL_LODGING", "TRAVEL_LODGING", 0.58),
    (
        "keyword_set",
        "meals,per diem",
        "IME.PHY_EXAM.TRAVEL_MEALS",
        "TRAVEL_MEALS",
        0.65,
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
