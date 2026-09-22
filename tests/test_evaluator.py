"""Evaluator self-tests.

These are candidate-created tests of the EVALUATOR, not product observations.
They verify that the assertion functions correctly detect faults and accept
valid response variations.

Three categories:
  - Faulty variants: deliberately broken responses that must trigger FAIL
  - Valid variations: meaning-preserving wording changes that must PASS
  - Assertion unit tests: targeted checks of individual assertion functions
"""

import pytest
import copy
from evaluator import assertions


# ============================================================================
# Fixtures: a known-good baseline recording
# ============================================================================

GOOD_BASELINE = {
    "id": "TEST_GOOD",
    "request": {
        "caller_id": "atlas-employee-01",
        "question": "What is my annual certification reimbursement limit?",
        "as_of": "2026-09-21"
    },
    "observed": {
        "http_status": 200,
        "body": {
            "status": "ANSWERED",
            "answer": "Your annual certification limit is INR 25,000.",
            "citations": [
                {"chunk_id": "P02", "quote": "The annual certification reimbursement limit for employees is INR 25000."}
            ]
        }
    },
    "trace": {
        "model_context_ids": ["P02"],
        "generation_attempts": 1,
        "provider_event": "success"
    }
}


def _mutate(recording: dict, **path_values) -> dict:
    """Deep-copy a recording and apply dotted-path mutations."""
    rec = copy.deepcopy(recording)
    for path, value in path_values.items():
        parts = path.split(".")
        obj = rec
        for p in parts[:-1]:
            if p.isdigit():
                obj = obj[int(p)]
            else:
                obj = obj[p]
        key = parts[-1]
        if key.isdigit():
            obj[int(key)] = value
        else:
            obj[key] = value
    return rec


# ============================================================================
# FAULTY VARIANT 1: Cross-tenant citation (cites Boreal passage for Atlas caller)
# ============================================================================

class TestFaultyVariant_CrossTenantCitation:
    """Evaluator must FAIL when a citation references a passage from wrong tenant."""

    def setup_method(self):
        self.rec = _mutate(
            GOOD_BASELINE,
            **{
                "id": "FAULT_CROSS_TENANT",
                "observed.body.answer": "Your annual certification limit is INR 80,000.",
                "observed.body.citations": [
                    {"chunk_id": "P06", "quote": "The annual certification reimbursement limit for employees is INR 80000."}
                ],
                "trace.model_context_ids": ["P06"],
            }
        )

    def test_citation_eligibility_fails(self):
        result = assertions.check_citation_eligibility(self.rec)
        assert result["verdict"] == "FAIL", f"Expected FAIL for cross-tenant citation, got {result}"

    def test_context_eligibility_fails(self):
        result = assertions.check_context_eligibility(self.rec)
        assert result["verdict"] == "FAIL", f"Expected FAIL for cross-tenant context, got {result}"


# ============================================================================
# FAULTY VARIANT 2: Misquoted citation
# ============================================================================

class TestFaultyVariant_MisquotedCitation:
    """Evaluator must FAIL when the quote text differs from the corpus."""

    def setup_method(self):
        self.rec = _mutate(
            GOOD_BASELINE,
            **{
                "id": "FAULT_MISQUOTE",
                "observed.body.citations": [
                    {"chunk_id": "P02", "quote": "The annual certification reimbursement limit for employees is INR 99999."}
                ],
            }
        )

    def test_quotation_integrity_fails(self):
        result = assertions.check_quotation_integrity(self.rec)
        assert result["verdict"] == "FAIL", f"Expected FAIL for misquoted citation, got {result}"


# ============================================================================
# FAULTY VARIANT 3: Provider timeout masked as INSUFFICIENT_EVIDENCE
# ============================================================================

class TestFaultyVariant_MaskedTimeout:
    """Evaluator must FAIL when a provider timeout returns HTTP 200."""

    def setup_method(self):
        self.rec = _mutate(
            GOOD_BASELINE,
            **{
                "id": "FAULT_MASKED_TIMEOUT",
                "observed.body.status": "INSUFFICIENT_EVIDENCE",
                "observed.body.answer": None,
                "observed.body.citations": [],
                "trace.provider_event": "timeout",
            }
        )

    def test_provider_failure_handling_fails(self):
        result = assertions.check_provider_failure_handling(self.rec)
        assert result["verdict"] == "FAIL", f"Expected FAIL for masked timeout, got {result}"


# ============================================================================
# VALID VARIATION 1: Wording change (meaning preserved)
# ============================================================================

class TestValidVariation_WordingChange:
    """Evaluator must PASS when answer wording varies but meaning is preserved."""

    def setup_method(self):
        self.rec = _mutate(
            GOOD_BASELINE,
            **{
                "id": "VALID_WORDING",
                "observed.body.answer": "The yearly certification reimbursement cap stands at twenty-five thousand Indian rupees (INR 25,000).",
            }
        )

    def test_required_facts_pass(self):
        result = assertions.check_required_facts(self.rec, ["certification reimbursement limit is INR 25000"])
        assert result["verdict"] == "PASS", f"Expected PASS for valid wording variation, got {result}"

    def test_all_structural_checks_pass(self):
        for check_fn in [
            assertions.check_citation_eligibility,
            assertions.check_quotation_integrity,
            assertions.check_context_eligibility,
            assertions.check_provider_failure_handling,
            assertions.check_no_financial_actions,
        ]:
            result = check_fn(self.rec)
            assert result["verdict"] == "PASS", f"{check_fn.__name__} unexpectedly FAIL: {result}"


# ============================================================================
# VALID VARIATION 2: Rupee symbol instead of INR prefix
# ============================================================================

class TestValidVariation_RupeeSymbol:
    """Evaluator must PASS when amount uses ₹ symbol instead of INR."""

    def setup_method(self):
        self.rec = _mutate(
            GOOD_BASELINE,
            **{
                "id": "VALID_SYMBOL",
                "observed.body.answer": "Your certification reimbursement limit is ₹25,000 per year.",
            }
        )

    def test_required_facts_pass(self):
        result = assertions.check_required_facts(self.rec, ["certification reimbursement limit is INR 25000"])
        assert result["verdict"] == "PASS", f"Expected PASS for ₹ symbol variation, got {result}"


# ============================================================================
# Unit tests for individual assertion functions
# ============================================================================

class TestCheckHttpStatus:
    def test_matching(self):
        rec = _mutate(GOOD_BASELINE, **{"observed.http_status": 200})
        assert assertions.check_http_status(rec, 200)["verdict"] == "PASS"

    def test_mismatch(self):
        rec = _mutate(GOOD_BASELINE, **{"observed.http_status": 200})
        assert assertions.check_http_status(rec, 503)["verdict"] == "FAIL"


class TestCheckConflictDetection:
    """Home-office allowance question with P07 + P08 contradicting should yield CONFLICT."""

    def test_conflict_not_detected(self):
        rec = {
            "id": "TEST_CONFLICT",
            "request": {
                "caller_id": "atlas-employee-01",
                "question": "What is my annual home-office allowance?",
                "as_of": "2026-09-21"
            },
            "observed": {
                "http_status": 200,
                "body": {
                    "status": "ANSWERED",
                    "answer": "The annual home-office allowance is INR 12,000.",
                    "citations": [{"chunk_id": "P07", "quote": "..."}]
                }
            },
            "trace": {"model_context_ids": ["P07", "P08"], "generation_attempts": 1, "provider_event": "success"}
        }
        result = assertions.check_conflict_detection(rec)
        assert result["verdict"] == "FAIL", f"Expected FAIL for undetected conflict, got {result}"


class TestCheckNoFinancialActions:
    def test_clean_answer(self):
        result = assertions.check_no_financial_actions(GOOD_BASELINE)
        assert result["verdict"] == "PASS"

    def test_approval_language(self):
        rec = _mutate(GOOD_BASELINE, **{
            "observed.body.answer": "Your claim is approved and payment is guaranteed."
        })
        result = assertions.check_no_financial_actions(rec)
        assert result["verdict"] == "FAIL"


class TestCheckErrorBodyStructure:
    def test_valid_error(self):
        rec = {
            "id": "TEST_ERR",
            "request": {"caller_id": "atlas-employee-01", "question": "   ", "as_of": "2026-09-21"},
            "observed": {
                "http_status": 400,
                "body": {"error": {"code": "INVALID_REQUEST", "message": "question must not be empty"}}
            },
            "trace": {"model_context_ids": [], "generation_attempts": 0, "provider_event": "not_called"}
        }
        result = assertions.check_error_body_structure(rec)
        assert result["verdict"] == "PASS"

    def test_error_with_business_fields(self):
        rec = {
            "id": "TEST_ERR_BAD",
            "request": {"caller_id": "atlas-employee-01", "question": "   ", "as_of": "2026-09-21"},
            "observed": {
                "http_status": 400,
                "body": {
                    "error": {"code": "INVALID_REQUEST", "message": "bad"},
                    "status": "ANSWERED",
                    "answer": "oops"
                }
            },
            "trace": {"model_context_ids": [], "generation_attempts": 0, "provider_event": "not_called"}
        }
        result = assertions.check_error_body_structure(rec)
        assert result["verdict"] == "FAIL"


class TestEligiblePassages:
    """Verify the date-boundary logic used throughout the evaluator."""

    def test_p01_not_eligible_on_boundary(self):
        """P01 effective_to=2026-06-01; as_of=2026-06-01 must NOT be eligible (strict <)."""
        from evaluator.loader import eligible_passages, load_corpus
        corpus = load_corpus()
        elig = eligible_passages(corpus, "Atlas", "employee", "2026-06-01")
        ids = {p["chunk_id"] for p in elig}
        assert "P01" not in ids, "P01 should not be eligible on its effective_to date"
        assert "P02" in ids, "P02 should be eligible starting on its effective_from date"

    def test_draft_excluded(self):
        from evaluator.loader import eligible_passages, load_corpus
        corpus = load_corpus()
        elig = eligible_passages(corpus, "Atlas", "employee", "2026-09-21")
        ids = {p["chunk_id"] for p in elig}
        assert "P04" not in ids, "Draft passage P04 must never be eligible"

    def test_cross_tenant_excluded(self):
        from evaluator.loader import eligible_passages, load_corpus
        corpus = load_corpus()
        elig = eligible_passages(corpus, "Atlas", "employee", "2026-09-21")
        ids = {p["chunk_id"] for p in elig}
        assert "P06" not in ids, "Boreal passage P06 must not be eligible for Atlas"
        assert "P12" not in ids, "Boreal passage P12 must not be eligible for Atlas"

    def test_role_filtering(self):
        from evaluator.loader import eligible_passages, load_corpus
        corpus = load_corpus()
        elig = eligible_passages(corpus, "Atlas", "contractor", "2026-09-21")
        ids = {p["chunk_id"] for p in elig}
        assert "P05" in ids, "P05 (contractor) should be eligible"
        assert "P02" not in ids, "P02 (employee) must not be eligible for contractor"
