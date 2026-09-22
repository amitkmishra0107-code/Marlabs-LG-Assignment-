#!/usr/bin/env python3
"""Evaluate all recordings and produce a machine-readable report.

Usage:
    python run_evaluator.py              # prints JSON report to stdout
    python run_evaluator.py --summary    # prints only the summary line

Exit codes:
    0  — all checks passed
    1  — at least one check failed
    2  — evaluator error
"""

import sys
import json

try:
    from evaluator.evaluator import run
except ImportError:
    sys.path.insert(0, ".")
    from evaluator.evaluator import run


def main():
    try:
        report = run()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(2)

    if "--summary" in sys.argv:
        rv = report["recording_verdicts"]
        print(f"Recordings: {report['recordings_pass']}/{report['recordings_total']} PASS  |  "
              f"Checks: {report['total_pass']}/{report['total_checks']} PASS")
        for rid, verdict in sorted(rv.items()):
            print(f"  {rid}: {verdict}")
    else:
        # Full JSON report
        print(json.dumps(report, indent=2))

    sys.exit(0 if report["total_fail"] == 0 else 1)


if __name__ == "__main__":
    main()
