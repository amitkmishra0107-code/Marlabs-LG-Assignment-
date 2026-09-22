"""Loads corpus, caller lookup, and recorded observations from JSON files."""

import json
from pathlib import Path
from datetime import date

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EXPECTED_DIR = Path(__file__).resolve().parent.parent / "expected"


def load_json(path: Path) -> list | dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_corpus() -> list[dict]:
    return load_json(DATA_DIR / "corpus.json")


def load_callers() -> dict:
    return load_json(DATA_DIR / "callers.json")


def load_recordings() -> list[dict]:
    return load_json(DATA_DIR / "recordings.json")


def load_expected_results() -> list[dict]:
    return load_json(EXPECTED_DIR / "expected_results.json")


def corpus_by_id(corpus: list[dict]) -> dict[str, dict]:
    return {p["chunk_id"]: p for p in corpus}


def eligible_passages(corpus: list[dict], tenant: str, role: str, as_of: str) -> list[dict]:
    """Return passages matching tenant, role, Approved state, and date window.

    Eligibility: state == 'Approved' AND tenant matches AND role matches
    AND effective_from <= as_of < effective_to (strict less-than on effective_to).
    """
    as_of_date = date.fromisoformat(as_of)
    result = []
    for p in corpus:
        if p["state"] != "Approved":
            continue
        if p["tenant"] != tenant or p["role"] != role:
            continue
        eff_from = date.fromisoformat(p["effective_from"])
        eff_to = date.fromisoformat(p["effective_to"])
        if eff_from <= as_of_date < eff_to:
            result.append(p)
    return result
