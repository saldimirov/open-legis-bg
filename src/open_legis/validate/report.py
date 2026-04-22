from __future__ import annotations

import datetime
import json
from dataclasses import asdict

from open_legis.validate import LayerResult

_SEVERITY_PREFIX = {"error": "  ✗", "warn": "  !", "info": "  ·"}


def print_report(results: list[LayerResult], verbose: bool = False) -> int:
    """Print terminal report. Returns error count."""
    total_errors = 0
    total_warnings = 0

    for result in results:
        errors = [i for i in result.issues if i.severity == "error"]
        warnings = [i for i in result.issues if i.severity == "warn"]
        total_errors += len(errors)
        total_warnings += len(warnings)

        stats_str = "  ".join(f"{k}={v}" for k, v in result.stats.items())
        status = "OK" if not errors else f"{len(errors)} errors"
        print(f"\n── {result.name.upper()} ── {status}  {stats_str}")

        to_show = result.issues if verbose else result.issues[:20]
        for issue in to_show:
            line = f"{_SEVERITY_PREFIX[issue.severity]} [{issue.code}] {issue.message}"
            if issue.path:
                line += f"\n      {issue.path}"
            if issue.detail:
                line += f"\n      {issue.detail}"
            print(line)

        if not verbose and len(result.issues) > 20:
            print(f"  ... {len(result.issues) - 20} more (use --verbose to see all)")

    print(f"\n{'─' * 60}")
    print(f"Total: {total_errors} errors, {total_warnings} warnings")
    return total_errors


def write_json_report(results: list[LayerResult], path: str) -> None:
    report = {
        "run_at": datetime.datetime.now().isoformat(),
        "summary": {
            "errors": sum(len([i for i in r.issues if i.severity == "error"]) for r in results),
            "warnings": sum(len([i for i in r.issues if i.severity == "warn"]) for r in results),
            "layers_run": len(results),
        },
        "layers": [
            {
                "name": r.name,
                "stats": r.stats,
                "issues": [asdict(i) for i in r.issues],
            }
            for r in results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
