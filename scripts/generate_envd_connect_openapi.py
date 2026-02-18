#!/usr/bin/env python3
"""
Generate OpenAPI spec from envd proto files using protoc-gen-connect-openapi.

Usage:
    python3 scripts/generate_envd_connect_openapi.py --infra-path /path/to/infra

Requires: buf, protoc-gen-connect-openapi on PATH.
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
SHELL_SCRIPT = SCRIPT_DIR / "generate_envd_openapi.sh"
SERVICES = ["filesystem", "process"]


def generate_envd_connect_openapi(infra_path: Path) -> dict:
    spec_dir = infra_path / "packages" / "envd" / "spec"
    merged = {"openapi": "3.1.0", "info": {}, "paths": {}, "components": {"schemas": {}}, "tags": []}
    tag_names = set()

    # Load the REST envd.yaml and merge its paths + components
    envd_yaml = spec_dir / "envd.yaml"
    if envd_yaml.exists():
        envd = yaml.safe_load(envd_yaml.read_text())
        merged["paths"].update(envd.get("paths") or {})
        envd_components = envd.get("components") or {}
        for section in ["securitySchemes", "schemas", "parameters", "responses", "requestBodies"]:
            if section in envd_components:
                merged["components"].setdefault(section, {}).update(envd_components[section])

    # Generate Connect RPC specs from proto files
    with tempfile.TemporaryDirectory() as tmpdir:
        for service in SERVICES:
            output = Path(tmpdir) / f"{service}.yaml"
            subprocess.run(
                [str(SHELL_SCRIPT), "--proto-dir", str(spec_dir / service), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            spec = yaml.safe_load(output.read_text())

            merged["paths"].update(spec.get("paths") or {})
            merged["components"]["schemas"].update((spec.get("components") or {}).get("schemas") or {})
            for tag in spec.get("tags") or []:
                if tag["name"] not in tag_names:
                    merged["tags"].append(tag)
                    tag_names.add(tag["name"])

    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--infra-path", type=Path, default=SCRIPT_DIR.parent.parent / "infra")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR.parent / "envd-connect-openapi.yaml")
    args = parser.parse_args()

    spec = generate_envd_connect_openapi(args.infra_path.resolve())

    with open(args.output, "w") as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Written {len(spec['paths'])} endpoints to {args.output}")


if __name__ == "__main__":
    main()
