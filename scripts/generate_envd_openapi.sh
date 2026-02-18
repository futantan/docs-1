#!/usr/bin/env bash
#
# Generate OpenAPI spec from a single envd proto subdirectory using protoc-gen-connect-openapi.
#
# Usage:
#   ./scripts/generate_envd_openapi.sh --proto-dir /path/to/infra/packages/envd/spec/filesystem --output out.yaml
#
# Prerequisites:
#   - buf CLI (https://buf.build/docs/installation)
#   - protoc-gen-connect-openapi (https://github.com/sudorandom/protoc-gen-connect-openapi)
#
# Install prerequisites:
#   brew install bufbuild/buf/buf
#   go install github.com/sudorandom/protoc-gen-connect-openapi@latest

set -euo pipefail

PROTO_DIR=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --proto-dir)
            PROTO_DIR="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 --proto-dir /path/to/proto/dir --output /path/to/output.yaml"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$PROTO_DIR" || -z "$OUTPUT" ]]; then
    echo "Error: --proto-dir and --output are required."
    exit 1
fi

if ! command -v buf &> /dev/null; then
    echo "Error: buf CLI not found. Install with: brew install bufbuild/buf/buf"
    exit 1
fi

if ! command -v protoc-gen-connect-openapi &> /dev/null; then
    echo "Error: protoc-gen-connect-openapi not found."
    echo "Install with: go install github.com/sudorandom/protoc-gen-connect-openapi@latest"
    exit 1
fi

if [[ ! -d "$PROTO_DIR" ]]; then
    echo "Error: Proto directory not found: $PROTO_DIR"
    exit 1
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

cat > "$TMPDIR/buf.gen.yaml" <<EOF
version: v1
plugins:
  - plugin: connect-openapi
    out: $TMPDIR
    opt:
      - path=output.yaml
      - format=yaml
EOF

(cd "$PROTO_DIR" && buf generate --template "$TMPDIR/buf.gen.yaml")

if [[ ! -f "$TMPDIR/output.yaml" ]]; then
    echo "Error: Generation failed — output file not created."
    exit 1
fi

cp "$TMPDIR/output.yaml" "$OUTPUT"
echo "Generated: $OUTPUT"
