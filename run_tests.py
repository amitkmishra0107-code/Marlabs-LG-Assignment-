#!/usr/bin/env python3
"""Run evaluator self-tests.

Usage:
    python run_tests.py

Exit codes:
    0  — all evaluator tests passed
    1  — at least one test failed
"""

import sys
import pytest

sys.exit(pytest.main(["-v", "tests/", "--tb=short"]))
