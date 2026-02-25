"""
Classification engine tests.
Tests both the built-in rule engine and DB-backed rule lookup.
"""

import pytest
from app.services.classification.rule_engine import classify_with_builtin_rules


class TestBuiltinRuleEngine:
    """Tests for classify_with_builtin_rules() — no DB required."""

    # ── IME ──────────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("description,expected_code", [
        ("IME Physician Examination - Dr. Johnson",         "IME.PHY_EXAM.PROF_FEE"),
        ("Independent Medical Examination - Orthopedic",    "IME.PHY_EXAM.PROF_FEE"),
        ("IME examination fee",                             "IME.PHY_EXAM.PROF_FEE"),
        ("IME Addendum Report",                             "IME.ADDENDUM.PROF_FEE"),
        ("Addendum to IME report",                          "IME.ADDENDUM.PROF_FEE"),
        ("Records Review No Exam",                          "IME.RECORDS_REVIEW.PROF_FEE"),
        ("Peer Review of treatment plan",                   "IME.PEER_REVIEW.PROF_FEE"),
        ("No-show Fee - claimant did not appear",           "IME.NO_SHOW.NO_SHOW_FEE"),
        ("IME Cancellation Fee - 48 hour notice",           "IME.CANCELLATION.CANCEL_FEE"),
        ("Multi-specialty IME panel - Ortho and Neuro",     "IME.MULTI_SPECIALTY.PROF_FEE"),
        ("Administrative scheduling coordination fee",      "IME.ADMIN.SCHEDULING_FEE"),
    ])
    def test_ime_classifications(self, description, expected_code):
        result = classify_with_builtin_rules(description)
        assert result.taxonomy_code == expected_code, (
            f"Expected {expected_code!r}, got {result.taxonomy_code!r} "
            f"for description: {description!r}"
        )

    # ── IA ───────────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("description,expected_code", [
        ("Field Adjusting Services - Daily Rate",       "IA.FIELD_ASSIGN.PROF_FEE"),
        ("Desk Assignment - file review and estimate",  "IA.DESK_ASSIGN.PROF_FEE"),
        ("Photo Documentation Services",               "IA.PHOTO_DOC.PROF_FEE"),
        ("Supplement Handling",                        "IA.SUPPLEMENT_HANDLING.PROF_FEE"),
        ("File Open Fee",                              "IA.ADMIN.FILE_OPEN_FEE"),
        ("Catastrophe Assignment Daily Rate",          "IA.CAT_ASSIGN.PROF_FEE"),
    ])
    def test_ia_classifications(self, description, expected_code):
        result = classify_with_builtin_rules(description)
        assert result.taxonomy_code == expected_code, (
            f"Expected {expected_code!r}, got {result.taxonomy_code!r} "
            f"for description: {description!r}"
        )

    # ── Mileage / travel ─────────────────────────────────────────────────────

    def test_mileage_classified(self):
        result = classify_with_builtin_rules("Mileage - 47 miles @ $0.60/mile")
        assert result.billing_component == "MILEAGE"

    def test_airfare_classified(self):
        result = classify_with_builtin_rules("Travel - Airfare to examination site")
        assert result.billing_component == "TRAVEL_TRANSPORT"

    def test_lodging_classified(self):
        result = classify_with_builtin_rules("Lodging - 1 night hotel")
        assert result.billing_component == "TRAVEL_LODGING"

    # ── Confidence levels ─────────────────────────────────────────────────────

    def test_high_confidence_on_clear_match(self):
        result = classify_with_builtin_rules("No-show Fee")
        assert result.confidence == "HIGH"
        assert result.confidence_weight >= 0.85

    def test_unrecognized_on_no_match(self):
        result = classify_with_builtin_rules("Completely unrecognizable service XYZ-999")
        assert result.confidence == "UNRECOGNIZED"
        assert result.taxonomy_code is None

    def test_returns_match_explanation(self):
        result = classify_with_builtin_rules("IME Physician Examination")
        assert result.match_explanation
        assert len(result.match_explanation) > 0

    # ── Case insensitivity ────────────────────────────────────────────────────

    def test_case_insensitive_matching(self):
        upper = classify_with_builtin_rules("IME PHYSICIAN EXAMINATION")
        lower = classify_with_builtin_rules("ime physician examination")
        assert upper.taxonomy_code == lower.taxonomy_code

    # ── Exact code matching ───────────────────────────────────────────────────

    def test_raw_code_does_not_affect_builtin_rules(self):
        """Built-in rules don't do exact code matching — that's DB rules only."""
        result = classify_with_builtin_rules(
            "Completely unknown description",
            raw_code="UNKNOWN-999"
        )
        assert result.confidence == "UNRECOGNIZED"
