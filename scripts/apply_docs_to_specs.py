#!/usr/bin/env python3
"""
Apply summary and description from ENDPOINT_POLISH to the infra source specs.

Uses ruamel.yaml for round-trip editing to preserve comments, formatting,
and key ordering in the original files.

Usage:
    python scripts/apply_docs_to_specs.py --infra-path /path/to/infra
"""

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

sys.path.insert(0, str(Path(__file__).parent))
from generate_openapi import ENDPOINT_POLISH, SANDBOX_ENDPOINT_POLISH  # noqa: E402

ryaml = YAML()
ryaml.preserve_quotes = True
ryaml.width = 200
ryaml.best_map_representor = True
# Match the original indentation style in the infra specs:
# 2-space mapping indent, 4-space sequence indent, 2-space sequence dash offset
ryaml.indent(mapping=2, sequence=4, offset=2)


def apply_to_spec(spec_path: Path, polish_map: dict) -> int:
    """Apply summary/description from a polish map to an OpenAPI spec file.

    Uses ruamel.yaml round-trip mode to preserve comments and formatting.
    """
    with open(spec_path) as f:
        spec = ryaml.load(f)

    changes = 0
    for polish_key, polish in polish_map.items():
        method, path_str = polish_key.split(" ", 1)
        method = method.lower()

        paths = spec.get("paths")
        if not paths:
            continue

        path_obj = paths.get(path_str)
        if not path_obj:
            continue

        op = path_obj.get(method)
        if op is None or not hasattr(op, "get"):
            continue

        if polish.get("summary"):
            # Insert summary before description if it doesn't exist
            if "summary" not in op:
                # Insert at position 0 (before description)
                items = list(op.keys())
                desc_idx = items.index("description") if "description" in items else 0
                op.insert(desc_idx, "summary", polish["summary"])
            else:
                op["summary"] = polish["summary"]
            changes += 1

        if polish.get("description"):
            op["description"] = polish["description"]
            changes += 1

    with open(spec_path, "w") as f:
        ryaml.dump(spec, f)

    return changes


def main():
    parser = argparse.ArgumentParser(
        description="Apply documentation to infra source specs"
    )
    parser.add_argument(
        "--infra-path", type=Path, required=True,
        help="Path to the infra repository",
    )
    args = parser.parse_args()

    infra = args.infra_path.resolve()
    rest_spec = infra / "spec" / "openapi.yml"
    envd_spec = infra / "packages" / "envd" / "spec" / "envd.yaml"

    if not rest_spec.exists():
        print(f"REST spec not found: {rest_spec}")
        sys.exit(1)
    if not envd_spec.exists():
        print(f"envd spec not found: {envd_spec}")
        sys.exit(1)

    n = apply_to_spec(rest_spec, ENDPOINT_POLISH)
    print(f"REST spec: {n} fields updated in {rest_spec}")

    n = apply_to_spec(envd_spec, SANDBOX_ENDPOINT_POLISH)
    print(f"envd spec: {n} fields updated in {envd_spec}")

    print("Done!")


if __name__ == "__main__":
    main()
