#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


VALID_RESULTS = {"success", "failure", "cancelled", "skipped"}


def component_result(value: str) -> tuple[str, str]:
    name, separator, result = value.rpartition("=")
    if not separator or not name or result not in VALID_RESULTS:
        raise argparse.ArgumentTypeError(
            "component results must use NAME=success|failure|cancelled|skipped"
        )
    return name, result


def overall_status(results: list[str]) -> str:
    if "failure" in results:
        return "failure"
    if "cancelled" in results:
        return "cancelled"
    if all(result == "success" for result in results):
        return "success"
    return "incomplete"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the cross-toolchain bootstrap status manifest."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--package", action="append", required=True, type=component_result)
    parser.add_argument("--verification", required=True, type=component_result)
    parser.add_argument("--architecture-report", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--packages-repository", required=True)
    parser.add_argument("--packages-ref", required=True)
    parser.add_argument("--run-repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--run-sha", required=True)
    parser.add_argument("--run-ref", required=True)
    parser.add_argument("--run-url", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    verification_name, verification_result = args.verification

    architecture = None
    if args.architecture_report and args.architecture_report.exists():
        with args.architecture_report.open(encoding="utf-8") as report:
            architecture = json.load(report)
    if verification_result == "success" and architecture is None:
        raise ValueError("successful architecture verification must provide its report")

    pipeline = [*args.package, args.verification]
    first_failure = next(
        (name for name, result in pipeline if result == "failure"), None
    )
    first_incomplete = next(
        (name for name, result in pipeline if result != "success"), None
    )
    results = [result for _, result in pipeline]

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflow": "mingw-cross-toolchain",
        "status": overall_status(results),
        "first_failure": first_failure,
        "first_incomplete": first_incomplete,
        "target": args.target,
        "source": {
            "repository": args.packages_repository,
            "ref": args.packages_ref,
        },
        "run": {
            "repository": args.run_repository,
            "id": args.run_id,
            "attempt": args.run_attempt,
            "sha": args.run_sha,
            "ref": args.run_ref,
            "url": args.run_url,
        },
        "packages": [
            {
                "component": name,
                "status": result,
                "artifact": name if result == "success" else None,
            }
            for name, result in args.package
        ],
        "verification": {
            "component": verification_name,
            "status": verification_result,
            "artifact": verification_name
            if verification_result == "success"
            else None,
            "evidence": architecture,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2)
        output.write("\n")

    failure = first_failure or "none"
    print(f"Bootstrap status: {manifest['status']}; first failure: {failure}")


if __name__ == "__main__":
    main()
