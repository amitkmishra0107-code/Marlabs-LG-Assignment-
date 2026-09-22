"""Main evaluator: runs all assertion checks against recordings and produces a report."""

import json
from evaluator.loader import load_recordings, load_expected_results
from evaluator import assertions


def evaluate_recording(recording: dict, expected: dict | None) -> list[dict]:
    """Run all applicable checks on a single recording. Returns list of check results."""
    results = []
    rec_id = recording["id"]
    http_status = recording["observed"]["http_status"]

    # Determine expected values from expected_results if available
    exp_http = expected["expected_http"] if expected else http_status
    exp_status = expected["expected_status"] if expected else recording["observed"]["body"].get("status")
    required_facts = expected.get("required_facts", []) if expected else []
    prohibited_claims = expected.get("prohibited_claims", []) if expected else []

    # 1. HTTP status
    results.append(assertions.check_http_status(recording, exp_http))

    # 2. Response status
    results.append(assertions.check_response_status(recording, exp_status))

    # 3. Citation eligibility (only for 200 responses)
    if http_status == 200:
        results.append(assertions.check_citation_eligibility(recording))

    # 4. Quotation integrity
    if http_status == 200:
        results.append(assertions.check_quotation_integrity(recording))

    # 5. Generation context eligibility
    results.append(assertions.check_context_eligibility(recording))

    # 6. Provider failure handling
    results.append(assertions.check_provider_failure_handling(recording))

    # 7. Prohibited claims
    results.append(assertions.check_prohibited_claims(recording, prohibited_claims))

    # 8. Required facts
    results.append(assertions.check_required_facts(recording, required_facts))

    # 9. Conflict detection
    if http_status == 200:
        results.append(assertions.check_conflict_detection(recording))

    # 10. Invalid request must not invoke generation
    results.append(assertions.check_no_generation_on_invalid(recording))

    # 11. Error body structure
    results.append(assertions.check_error_body_structure(recording))

    # 12. Financial action prohibition
    results.append(assertions.check_no_financial_actions(recording))

    # Tag every result with recording ID
    for r in results:
        r["recording_id"] = rec_id

    return results


def evaluate_all(recordings: list[dict], expected_list: list[dict]) -> list[dict]:
    """Evaluate all recordings. Returns flat list of check results."""
    expected_map = {e["recording_id"]: e for e in expected_list}
    all_results = []
    for rec in recordings:
        expected = expected_map.get(rec["id"])
        all_results.extend(evaluate_recording(rec, expected))
    return all_results


def summary_report(results: list[dict]) -> dict:
    """Produce a summary report from check results."""
    by_recording: dict[str, dict] = {}
    for r in results:
        rid = r["recording_id"]
        if rid not in by_recording:
            by_recording[rid] = {"recording_id": rid, "checks": [], "pass": 0, "fail": 0}
        by_recording[rid]["checks"].append(r)
        if r["verdict"] == "PASS":
            by_recording[rid]["pass"] += 1
        else:
            by_recording[rid]["fail"] += 1

    total_pass = sum(r["verdict"] == "PASS" for r in results)
    total_fail = sum(r["verdict"] == "FAIL" for r in results)

    recording_verdicts = {}
    for rid, data in by_recording.items():
        recording_verdicts[rid] = "PASS" if data["fail"] == 0 else "FAIL"

    return {
        "total_checks": len(results),
        "total_pass": total_pass,
        "total_fail": total_fail,
        "recording_verdicts": recording_verdicts,
        "recordings_pass": sum(1 for v in recording_verdicts.values() if v == "PASS"),
        "recordings_fail": sum(1 for v in recording_verdicts.values() if v == "FAIL"),
        "recordings_total": len(recording_verdicts),
        "details": results,
    }


def run() -> dict:
    """Load data, evaluate, return full report."""
    recordings = load_recordings()
    expected = load_expected_results()
    results = evaluate_all(recordings, expected)
    return summary_report(results)
