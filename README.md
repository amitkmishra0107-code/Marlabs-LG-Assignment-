# Marlabs GenAI QA — Policy Assistant Evaluation Pack

QA evaluation pack for an AI policy assistant prototype. Assesses release readiness for a controlled internal pilot based on 12 synthetic recorded observations, a 12-passage policy corpus, and the API contract.

## Repository Structure

```
├── data/
│   ├── corpus.json           # P01–P12 synthetic policy passages (unchanged)
│   ├── callers.json          # X-Caller-Id → tenant/role lookup
│   └── recordings.json       # R01–R12 faithful transcriptions of observed responses
├── expected/
│   └── expected_results.json # Independently derived expected results with rationale
├── inventory/
│   └── test_inventory.md     # Risk-prioritized test inventory (12 recorded + 12 designed)
├── evaluator/
│   ├── __init__.py
│   ├── loader.py             # Fixture loader for corpus, callers, recordings
│   ├── assertions.py         # 12 reusable assertion functions
│   └── evaluator.py          # Orchestrator: runs all checks, produces report
├── tests/
│   ├── conftest.py
│   └── test_evaluator.py     # Evaluator self-tests: 3 faulty variants + 2 valid variations
├── reports/
│   └── defects.md            # 5 defect reports + release recommendation (NO GO)
├── run_evaluator.py          # Entry point: evaluate recordings
├── run_tests.py              # Entry point: test the evaluator
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Evaluate the recorded observations (exit code 1 = failures found)
python run_evaluator.py --summary

# Full JSON report
python run_evaluator.py > report.json

# Run evaluator self-tests (exit code 0 = all tests pass)
python run_tests.py
```

## Exit Code Behavior

| Command | Exit 0 | Exit 1 | Exit 2 |
|---------|--------|--------|--------|
| `run_evaluator.py` | All checks PASS | At least one FAIL | Evaluator error |
| `run_tests.py` | All pytest tests PASS | At least one test FAIL | — |

## What the Evaluator Checks

12 reusable assertion functions across these categories:

| Category | Assertions |
|----------|-----------|
| Response contract | `check_http_status`, `check_response_status`, `check_error_body_structure` |
| Evidence eligibility | `check_citation_eligibility`, `check_context_eligibility` |
| Quotation integrity | `check_quotation_integrity` |
| Provider failure handling | `check_provider_failure_handling` |
| Answer content | `check_required_facts`, `check_prohibited_claims`, `check_no_financial_actions` |
| Conflict detection | `check_conflict_detection` |
| Input validation | `check_no_generation_on_invalid` |

## Evaluator Self-Tests

The test suite (`tests/test_evaluator.py`) contains candidate-created tests of the evaluator itself:

- **3 faulty variants** (deliberately broken responses): cross-tenant citation, misquoted citation, masked provider timeout
- **2 valid variations** (meaning-preserving changes): wording variation, rupee symbol notation
- **Unit tests** for date-boundary logic, conflict detection, financial-action check, error body validation

These verify that the evaluator catches known-bad responses and accepts valid wording changes. They are evaluator tests, not product observations.

## Results Summary

- **Recordings evaluated:** 12
- **Recording-level verdicts:** 4 PASS, 8 FAIL
- **Release recommendation:** NO GO (3 blockers, 2 critical defects)
- **Designed but not executed:** 12 additional test cases (require live endpoint)

See `reports/defects.md` for full defect reports and release rationale.

## Limitations

- Evaluated against 12 synthetic recordings only; no live endpoint tested.
- Cannot establish latency, capacity, or production response distribution.
- Answer-meaning checks use numeric extraction and keyword matching, not NLP. Manual review was applied for semantic equivalence judgments documented in expected results.
- Conflict detection uses keyword-based topic grouping, suitable for this corpus but not generalizable.
- The prompt-injection passage P11 was never tested as a retrieval input.

## Dependencies

- Python 3.10+
- pytest >= 7.0
- No paid APIs, cloud accounts, or external datasets required.

## AI Assistance

This evaluation pack was built with AI coding assistance (Claude). All test judgments, expected results, defect assessments, and the release recommendation were reviewed and validated by the candidate.

## Time Spent

Approximately 4 hours.
