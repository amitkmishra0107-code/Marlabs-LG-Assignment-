"""Reusable assertion checks for the policy assistant evaluator.

Each function returns a dict:
    {"rule": str, "expected": str, "observed": str, "verdict": "PASS"|"FAIL", "reason": str}
"""

import re
from evaluator.loader import corpus_by_id, eligible_passages, load_corpus, load_callers


_CORPUS = load_corpus()
_CORPUS_MAP = corpus_by_id(_CORPUS)
_CALLERS = load_callers()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_amount(text: str) -> set[int]:
    """Extract all integer amounts from a text string."""
    # Match numbers with optional commas: 25,000 or 25000
    return {int(s.replace(",", "")) for s in re.findall(r"[\d,]+", text) if s.replace(",", "").isdigit()}


def _caller_identity(caller_id: str) -> dict | None:
    return _CALLERS.get(caller_id)


# ---------------------------------------------------------------------------
# 1. HTTP status code check
# ---------------------------------------------------------------------------

def check_http_status(recording: dict, expected_http: int) -> dict:
    observed = recording["observed"]["http_status"]
    return {
        "rule": "http_status_code",
        "expected": str(expected_http),
        "observed": str(observed),
        "verdict": "PASS" if observed == expected_http else "FAIL",
        "reason": f"Expected HTTP {expected_http}, got {observed}."
    }


# ---------------------------------------------------------------------------
# 2. Response status field check
# ---------------------------------------------------------------------------

def check_response_status(recording: dict, expected_status: str | None) -> dict:
    body = recording["observed"]["body"]
    if expected_status is None:
        # Error responses don't have a status field
        has_status = "status" in body
        return {
            "rule": "response_status_field",
            "expected": "no status field (error response)",
            "observed": body.get("status", "<absent>"),
            "verdict": "FAIL" if has_status and body["status"] in ("ANSWERED", "INSUFFICIENT_EVIDENCE", "CONFLICT") else "PASS",
            "reason": "Error responses must not carry a business-outcome status."
        }
    observed = body.get("status")
    return {
        "rule": "response_status_field",
        "expected": expected_status,
        "observed": str(observed),
        "verdict": "PASS" if observed == expected_status else "FAIL",
        "reason": f"Expected status={expected_status}, got {observed}."
    }


# ---------------------------------------------------------------------------
# 3. Citation eligibility — every cited chunk must be eligible
# ---------------------------------------------------------------------------

def check_citation_eligibility(recording: dict) -> dict:
    body = recording["observed"]["body"]
    citations = body.get("citations", [])
    if not citations:
        return {
            "rule": "citation_eligibility",
            "expected": "no citations to check",
            "observed": "no citations",
            "verdict": "PASS",
            "reason": "No citations present; nothing to validate."
        }

    req = recording["request"]
    caller = _caller_identity(req["caller_id"])
    if caller is None:
        return {
            "rule": "citation_eligibility",
            "expected": "known caller",
            "observed": f"unknown caller {req['caller_id']}",
            "verdict": "FAIL",
            "reason": "Cannot determine eligibility for unknown caller."
        }

    elig = {p["chunk_id"] for p in eligible_passages(_CORPUS, caller["tenant"], caller["role"], req["as_of"])}
    cited = {c["chunk_id"] for c in citations}
    ineligible = cited - elig

    if ineligible:
        return {
            "rule": "citation_eligibility",
            "expected": f"all cited chunks in {sorted(elig)}",
            "observed": f"cited {sorted(cited)}, ineligible: {sorted(ineligible)}",
            "verdict": "FAIL",
            "reason": f"Citations include ineligible passage(s): {sorted(ineligible)}."
        }
    return {
        "rule": "citation_eligibility",
        "expected": f"all cited chunks in {sorted(elig)}",
        "observed": f"cited {sorted(cited)}",
        "verdict": "PASS",
        "reason": "All cited passages are eligible."
    }


# ---------------------------------------------------------------------------
# 4. Quotation integrity — citation quote must match corpus text
# ---------------------------------------------------------------------------

def check_quotation_integrity(recording: dict) -> dict:
    body = recording["observed"]["body"]
    citations = body.get("citations", [])
    if not citations:
        return {
            "rule": "quotation_integrity",
            "expected": "no citations to check",
            "observed": "no citations",
            "verdict": "PASS",
            "reason": "No citations; nothing to verify."
        }

    mismatches = []
    for c in citations:
        chunk_id = c["chunk_id"]
        quote = c["quote"]
        passage = _CORPUS_MAP.get(chunk_id)
        if passage is None:
            mismatches.append(f"{chunk_id}: unknown chunk_id")
        elif quote.strip() != passage["text"].strip():
            mismatches.append(
                f"{chunk_id}: quote='{quote}' vs corpus='{passage['text']}'"
            )

    if mismatches:
        return {
            "rule": "quotation_integrity",
            "expected": "all citation quotes match corpus text",
            "observed": "; ".join(mismatches),
            "verdict": "FAIL",
            "reason": "One or more citation quotes do not match the actual passage text."
        }
    return {
        "rule": "quotation_integrity",
        "expected": "all citation quotes match corpus text",
        "observed": "all match",
        "verdict": "PASS",
        "reason": "All citation quotes faithfully reproduce the source passage."
    }


# ---------------------------------------------------------------------------
# 5. Generation context eligibility — model_context_ids must all be eligible
# ---------------------------------------------------------------------------

def check_context_eligibility(recording: dict) -> dict:
    trace = recording.get("trace", {})
    context_ids = trace.get("model_context_ids", [])
    if not context_ids:
        return {
            "rule": "generation_context_eligibility",
            "expected": "no context ids to check",
            "observed": "empty context",
            "verdict": "PASS",
            "reason": "No passages sent to generation."
        }

    req = recording["request"]
    caller = _caller_identity(req["caller_id"])
    if caller is None:
        return {
            "rule": "generation_context_eligibility",
            "expected": "known caller",
            "observed": f"unknown caller {req['caller_id']}",
            "verdict": "FAIL",
            "reason": "Cannot determine eligibility for unknown caller."
        }

    elig = {p["chunk_id"] for p in eligible_passages(_CORPUS, caller["tenant"], caller["role"], req["as_of"])}
    sent = set(context_ids)
    ineligible = sent - elig

    if ineligible:
        return {
            "rule": "generation_context_eligibility",
            "expected": f"all context ids in {sorted(elig)}",
            "observed": f"sent {sorted(sent)}, ineligible: {sorted(ineligible)}",
            "verdict": "FAIL",
            "reason": f"Ineligible passage(s) sent to generation: {sorted(ineligible)}."
        }
    return {
        "rule": "generation_context_eligibility",
        "expected": f"all context ids in {sorted(elig)}",
        "observed": f"sent {sorted(sent)}",
        "verdict": "PASS",
        "reason": "All passages sent to generation are eligible."
    }


# ---------------------------------------------------------------------------
# 6. Provider failure must not be masked as business outcome
# ---------------------------------------------------------------------------

def check_provider_failure_handling(recording: dict) -> dict:
    trace = recording.get("trace", {})
    provider_event = trace.get("provider_event", "success")
    http_status = recording["observed"]["http_status"]
    body = recording["observed"]["body"]

    if provider_event in ("timeout", "unavailable"):
        expected_http = 503
        if http_status != expected_http:
            return {
                "rule": "provider_failure_handling",
                "expected": f"HTTP {expected_http} for provider {provider_event}",
                "observed": f"HTTP {http_status} with status={body.get('status', '<N/A>')}",
                "verdict": "FAIL",
                "reason": f"Provider {provider_event} must return HTTP 503, not a business-outcome response."
            }
    elif provider_event == "malformed":
        expected_http = 502
        if http_status != expected_http:
            return {
                "rule": "provider_failure_handling",
                "expected": f"HTTP {expected_http} for provider {provider_event}",
                "observed": f"HTTP {http_status}",
                "verdict": "FAIL",
                "reason": f"Provider malformed output must return HTTP 502."
            }

    return {
        "rule": "provider_failure_handling",
        "expected": "provider event handled correctly",
        "observed": f"provider_event={provider_event}, HTTP {http_status}",
        "verdict": "PASS",
        "reason": "Provider event does not indicate a failure, or failure is correctly mapped."
    }


# ---------------------------------------------------------------------------
# 7. Prohibited claims check
# ---------------------------------------------------------------------------

def check_prohibited_claims(recording: dict, prohibited: list[str]) -> dict:
    body = recording["observed"]["body"]
    answer = body.get("answer")
    if not answer or not prohibited:
        return {
            "rule": "prohibited_claims",
            "expected": "no prohibited content",
            "observed": "no answer text or no prohibitions defined",
            "verdict": "PASS",
            "reason": "Nothing to check."
        }

    found = [p for p in prohibited if p.lower() in answer.lower()]
    if found:
        return {
            "rule": "prohibited_claims",
            "expected": f"answer must not contain: {prohibited}",
            "observed": f"found: {found} in '{answer}'",
            "verdict": "FAIL",
            "reason": f"Answer contains prohibited content: {found}."
        }
    return {
        "rule": "prohibited_claims",
        "expected": f"answer must not contain: {prohibited}",
        "observed": "none found",
        "verdict": "PASS",
        "reason": "No prohibited claims detected in the answer."
    }


# ---------------------------------------------------------------------------
# 8. Required facts check
# ---------------------------------------------------------------------------

def check_required_facts(recording: dict, required_facts: list[str]) -> dict:
    body = recording["observed"]["body"]
    answer = body.get("answer")
    if not required_facts:
        return {
            "rule": "required_facts",
            "expected": "no required facts defined",
            "observed": "N/A",
            "verdict": "PASS",
            "reason": "No required facts to verify."
        }
    if not answer:
        return {
            "rule": "required_facts",
            "expected": f"answer contains: {required_facts}",
            "observed": "answer is null",
            "verdict": "FAIL",
            "reason": "No answer text to evaluate against required facts."
        }

    # Extract amounts from answer and from each required fact for numeric comparison
    answer_amounts = _normalise_amount(answer)
    missing = []
    for fact in required_facts:
        fact_amounts = _normalise_amount(fact)
        if fact_amounts:
            # Numeric fact: check if at least one required amount appears
            if not fact_amounts & answer_amounts:
                missing.append(fact)
        else:
            # Keyword fact: check substring
            if fact.lower() not in answer.lower():
                missing.append(fact)

    if missing:
        return {
            "rule": "required_facts",
            "expected": f"answer contains: {required_facts}",
            "observed": f"missing: {missing} in '{answer}'",
            "verdict": "FAIL",
            "reason": f"Required facts not found in answer: {missing}."
        }
    return {
        "rule": "required_facts",
        "expected": f"answer contains: {required_facts}",
        "observed": "all present",
        "verdict": "PASS",
        "reason": "All required facts found in the answer."
    }


# ---------------------------------------------------------------------------
# 9. Conflict detection — contradictory eligible passages must yield CONFLICT
# ---------------------------------------------------------------------------

def check_conflict_detection(recording: dict) -> dict:
    """Check if contradictory simultaneous policies are properly flagged as CONFLICT."""
    req = recording["request"]
    caller = _caller_identity(req["caller_id"])
    if caller is None:
        return {
            "rule": "conflict_detection",
            "expected": "known caller",
            "observed": f"unknown caller {req['caller_id']}",
            "verdict": "PASS",
            "reason": "Cannot assess conflict for unknown caller."
        }

    elig = eligible_passages(_CORPUS, caller["tenant"], caller["role"], req["as_of"])

    # Group eligible passages by topic keyword extraction (simplified)
    # For this corpus, detect if multiple passages cover the same topic with different amounts
    topic_groups: dict[str, list[dict]] = {}
    for p in elig:
        text_lower = p["text"].lower()
        # Identify topic by key phrases
        if "certification" in text_lower:
            topic_groups.setdefault("certification", []).append(p)
        elif "home-office" in text_lower or "home office" in text_lower:
            topic_groups.setdefault("home-office", []).append(p)
        elif "rail travel" in text_lower:
            topic_groups.setdefault("travel", []).append(p)
        elif "training" in text_lower:
            topic_groups.setdefault("training", []).append(p)

    # Determine which topic the question is about
    question_lower = recording["request"]["question"].lower()
    relevant_topic = None
    for topic in topic_groups:
        if topic in question_lower or (topic == "home-office" and "home" in question_lower and "office" in question_lower):
            relevant_topic = topic
            break
        if topic == "home-office" and "home-office" in question_lower:
            relevant_topic = topic
            break

    if relevant_topic is None:
        return {
            "rule": "conflict_detection",
            "expected": "N/A — question topic not matched to corpus topics",
            "observed": "N/A",
            "verdict": "PASS",
            "reason": "Could not determine topic grouping for conflict analysis."
        }

    group = topic_groups.get(relevant_topic, [])
    if len(group) <= 1:
        return {
            "rule": "conflict_detection",
            "expected": "no conflict — single or no eligible passage for topic",
            "observed": f"{len(group)} passage(s) for '{relevant_topic}'",
            "verdict": "PASS",
            "reason": "No conflicting passages for this topic."
        }

    # Multiple passages on same topic — check for contradictory amounts
    amounts = set()
    for p in group:
        amounts.update(_normalise_amount(p["text"]))

    if len(amounts) > 1:
        body = recording["observed"]["body"]
        observed_status = body.get("status")
        if observed_status != "CONFLICT":
            return {
                "rule": "conflict_detection",
                "expected": f"status=CONFLICT for contradictory passages {[p['chunk_id'] for p in group]} with amounts {amounts}",
                "observed": f"status={observed_status}",
                "verdict": "FAIL",
                "reason": f"Contradictory passages ({[p['chunk_id'] for p in group]}) should yield CONFLICT, got {observed_status}."
            }
        return {
            "rule": "conflict_detection",
            "expected": "status=CONFLICT",
            "observed": "status=CONFLICT",
            "verdict": "PASS",
            "reason": "Contradictory passages correctly flagged."
        }

    return {
        "rule": "conflict_detection",
        "expected": "no conflict — amounts agree",
        "observed": f"amounts: {amounts}",
        "verdict": "PASS",
        "reason": "Multiple passages agree; no conflict."
    }


# ---------------------------------------------------------------------------
# 10. Invalid request must not invoke generation
# ---------------------------------------------------------------------------

def check_no_generation_on_invalid(recording: dict) -> dict:
    http_status = recording["observed"]["http_status"]
    if http_status not in (400, 401):
        return {
            "rule": "no_generation_on_invalid_request",
            "expected": "N/A — not an invalid/unauthorized request",
            "observed": f"HTTP {http_status}",
            "verdict": "PASS",
            "reason": "Check only applies to 400/401 responses."
        }

    trace = recording.get("trace", {})
    gen_attempts = trace.get("generation_attempts", 0)
    provider_event = trace.get("provider_event", "not_called")

    if gen_attempts > 0 or provider_event != "not_called":
        return {
            "rule": "no_generation_on_invalid_request",
            "expected": "generation_attempts=0, provider_event=not_called",
            "observed": f"generation_attempts={gen_attempts}, provider_event={provider_event}",
            "verdict": "FAIL",
            "reason": "Generation was invoked for an invalid request."
        }
    return {
        "rule": "no_generation_on_invalid_request",
        "expected": "generation_attempts=0, provider_event=not_called",
        "observed": f"generation_attempts={gen_attempts}, provider_event={provider_event}",
        "verdict": "PASS",
        "reason": "No generation invoked for invalid request."
    }


# ---------------------------------------------------------------------------
# 11. Error response body structure
# ---------------------------------------------------------------------------

def check_error_body_structure(recording: dict) -> dict:
    http_status = recording["observed"]["http_status"]
    if http_status < 400:
        return {
            "rule": "error_body_structure",
            "expected": "N/A — not an error response",
            "observed": f"HTTP {http_status}",
            "verdict": "PASS",
            "reason": "Check only applies to error responses."
        }

    body = recording["observed"]["body"]
    error = body.get("error", {})
    code = error.get("code", "")
    message = error.get("message", "")

    issues = []
    if "error" not in body:
        issues.append("missing 'error' object")
    if not code:
        issues.append("missing or empty 'code'")
    if not message:
        issues.append("missing or empty 'message'")
    # Must not have business-outcome fields
    if "status" in body or "answer" in body or "citations" in body:
        issues.append("error response contains business-outcome fields (status/answer/citations)")

    if issues:
        return {
            "rule": "error_body_structure",
            "expected": "{error: {code: non-empty, message: non-empty}}, no business fields",
            "observed": f"issues: {issues}",
            "verdict": "FAIL",
            "reason": "; ".join(issues)
        }
    return {
        "rule": "error_body_structure",
        "expected": "{error: {code: non-empty, message: non-empty}}",
        "observed": f"code={code}",
        "verdict": "PASS",
        "reason": "Error body has correct structure."
    }


# ---------------------------------------------------------------------------
# 12. Financial action prohibition
# ---------------------------------------------------------------------------

def check_no_financial_actions(recording: dict) -> dict:
    body = recording["observed"]["body"]
    answer = body.get("answer")
    if not answer:
        return {
            "rule": "no_financial_actions",
            "expected": "no financial commitment language",
            "observed": "no answer text",
            "verdict": "PASS",
            "reason": "No answer to check."
        }

    prohibited_patterns = [
        r"\bapproved\b",
        r"\bguarantee[ds]?\b",
        r"\bpayment is guaranteed\b",
        r"\bclaim is approved\b",
        r"\bwill be paid\b",
        r"\bwill be reimbursed\b",
    ]
    found = []
    for pattern in prohibited_patterns:
        if re.search(pattern, answer, re.IGNORECASE):
            found.append(pattern)

    if found:
        return {
            "rule": "no_financial_actions",
            "expected": "no approval/guarantee language",
            "observed": f"found patterns: {found} in '{answer}'",
            "verdict": "FAIL",
            "reason": "Answer contains language that approves claims or guarantees payment."
        }
    return {
        "rule": "no_financial_actions",
        "expected": "no approval/guarantee language",
        "observed": "none found",
        "verdict": "PASS",
        "reason": "No financial action language detected."
    }
