#!/usr/bin/env python3
"""Generate a merged OpenAPI spec for the full E2B developer-facing API.

Fetches specs from e2b-dev/infra at specified commits (or latest main),
combines multiple sources into a single openapi-public.yml:

  Sandbox API (served on <port>-<sandboxID>.e2b.app):
    - Proto-generated OpenAPI for process/filesystem Connect RPC
    - Hand-written REST spec (packages/envd/spec/envd.yaml)
    - Auto-generated stubs for streaming RPCs (parsed from .proto files)

  Platform API (served on api.e2b.app):
    - Main E2B API spec (spec/openapi.yml)

Usage:
    python3 scripts/generate_openapi_reference.py [options]

Options:
    --envd-commit HASH   Commit/branch/tag in e2b-dev/infra for envd specs (default: main)
    --api-commit HASH    Commit/branch/tag in e2b-dev/infra for platform API spec (default: main)
    --output FILE        Output path (default: openapi-public.yml in repo root)

Requires: Docker, PyYAML (pip install pyyaml).
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from glob import glob
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

INFRA_REPO = "https://github.com/e2b-dev/infra.git"

# Paths within e2b-dev/infra
INFRA_ENVD_SPEC_DIR = "packages/envd/spec"
INFRA_ENVD_REST_SPEC = "packages/envd/spec/envd.yaml"
INFRA_API_SPEC = "spec/openapi.yml"

DOCKER_IMAGE = "e2b-openapi-generator"

DOCKERFILE = """\
FROM golang:1.25-alpine
RUN apk add --no-cache git
RUN go install github.com/bufbuild/buf/cmd/buf@v1.50.0
RUN go install github.com/sudorandom/protoc-gen-connect-openapi@v0.25.3
ENV PATH="/go/bin:${PATH}"
"""

BUF_GEN_YAML = """\
version: v1
plugins:
  - plugin: connect-openapi
    out: /output/generated
    opt:
      - format=yaml
"""

# Server definitions for the two API surfaces
SANDBOX_SERVER = {
    "url": "https://{port}-{sandboxID}.e2b.app",
    "description": "Sandbox API (envd) — runs inside each sandbox",
    "variables": {
        "port": {"default": "49983", "description": "Port number"},
        "sandboxID": {"default": "$SANDBOX_ID", "description": "Sandbox identifier"},
    },
}

PLATFORM_SERVER = {
    "url": "https://api.e2b.app",
    "description": "E2B Platform API",
}

# Tag used to mark sandbox-specific paths so we can attach the right server
SANDBOX_TAG = "x-e2b-server"

# Security scheme name for envd endpoints (must not collide with platform's AccessTokenAuth)
SANDBOX_AUTH_SCHEME = "SandboxAccessTokenAuth"

# ---------------------------------------------------------------------------
# Proto parsing — auto-detect streaming RPCs
# ---------------------------------------------------------------------------

@dataclass
class RpcMethod:
    """An RPC method parsed from a .proto file."""

    package: str
    service: str
    method: str
    request_type: str
    response_type: str
    client_streaming: bool
    server_streaming: bool
    comment: str

    @property
    def path(self) -> str:
        return f"/{self.package}.{self.service}/{self.method}"

    @property
    def tag(self) -> str:
        return f"{self.package}.{self.service}"

    @property
    def operation_id(self) -> str:
        return f"{self.package}.{self.service}.{self.method}"

    @property
    def request_schema_ref(self) -> str:
        return f"#/components/schemas/{self.package}.{self.request_type}"

    @property
    def response_schema_ref(self) -> str:
        return f"#/components/schemas/{self.package}.{self.response_type}"

    @property
    def is_streaming(self) -> bool:
        return self.client_streaming or self.server_streaming

    @property
    def streaming_label(self) -> str:
        if self.client_streaming and self.server_streaming:
            return "Bidirectional-streaming"
        if self.client_streaming:
            return "Client-streaming"
        if self.server_streaming:
            return "Server-streaming"
        return "Unary"


_PACKAGE_RE = re.compile(r"^package\s+(\w+)\s*;", re.MULTILINE)
_SERVICE_RE = re.compile(r"service\s+(\w+)\s*\{", re.MULTILINE)
_RPC_RE = re.compile(
    r"rpc\s+(\w+)\s*\(\s*(stream\s+)?(\w+)\s*\)\s*returns\s*\(\s*(stream\s+)?(\w+)\s*\)"
)


def parse_proto_file(path: str) -> list[RpcMethod]:
    """Parse a .proto file and return all RPC methods found."""
    with open(path) as f:
        content = f.read()

    pkg_match = _PACKAGE_RE.search(content)
    if not pkg_match:
        return []
    package = pkg_match.group(1)

    methods: list[RpcMethod] = []

    for svc_match in _SERVICE_RE.finditer(content):
        service_name = svc_match.group(1)
        brace_start = content.index("{", svc_match.start())
        depth, pos = 1, brace_start + 1
        while depth > 0 and pos < len(content):
            if content[pos] == "{":
                depth += 1
            elif content[pos] == "}":
                depth -= 1
            pos += 1
        service_body = content[brace_start:pos]

        for rpc_match in _RPC_RE.finditer(service_body):
            rpc_start = service_body.rfind("\n", 0, rpc_match.start())
            comment = _extract_comment(service_body, rpc_start)

            methods.append(RpcMethod(
                package=package,
                service=service_name,
                method=rpc_match.group(1),
                request_type=rpc_match.group(3),
                response_type=rpc_match.group(5),
                client_streaming=bool(rpc_match.group(2)),
                server_streaming=bool(rpc_match.group(4)),
                comment=comment,
            ))

    return methods


def _extract_comment(text: str, before_pos: int) -> str:
    """Extract // comment lines immediately above a position in text."""
    lines = text[:before_pos].rstrip().split("\n")
    comment_lines: list[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("//"):
            comment_lines.append(stripped.lstrip("/ "))
        elif stripped == "":
            continue
        else:
            break
    comment_lines.reverse()
    return " ".join(comment_lines)


def find_streaming_rpcs(spec_dir: str) -> list[RpcMethod]:
    """Scan all .proto files under spec_dir and return streaming RPCs."""
    streaming: list[RpcMethod] = []
    for proto_path in sorted(glob(os.path.join(spec_dir, "**/*.proto"), recursive=True)):
        for rpc in parse_proto_file(proto_path):
            if rpc.is_streaming:
                streaming.append(rpc)
    return streaming


def build_streaming_path(rpc: RpcMethod) -> dict[str, Any]:
    """Build an OpenAPI path item for a streaming RPC."""
    description = (
        f"{rpc.streaming_label} RPC. "
        f"{rpc.comment + '. ' if rpc.comment else ''}"
        f"Use the Connect protocol with streaming support."
    )
    return {
        "post": {
            "tags": [rpc.tag],
            "summary": rpc.method,
            "description": description,
            "operationId": rpc.operation_id,
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": rpc.request_schema_ref}
                    }
                },
                "required": True,
            },
            "responses": {
                "200": {
                    "description": f"Stream of {rpc.response_type} events",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": rpc.response_schema_ref}
                        }
                    },
                },
            },
        }
    }


# ---------------------------------------------------------------------------
# Docker: fetch specs from e2b-dev/infra and generate OpenAPI from protos
# ---------------------------------------------------------------------------

def docker_build_image() -> None:
    """Build the Docker image with buf + protoc-gen-connect-openapi."""
    print("==> Building Docker image")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
        f.write(DOCKERFILE)
        dockerfile_path = f.name
    try:
        subprocess.run(
            ["docker", "build", "-t", DOCKER_IMAGE, "-f", dockerfile_path, "."],
            check=True,
            cwd=DOCS_REPO_ROOT,
        )
    finally:
        os.unlink(dockerfile_path)


@dataclass
class FetchedSpecs:
    """Paths to specs fetched from e2b-dev/infra."""
    envd_spec_dir: str       # directory containing .proto files
    envd_rest_spec: str      # path to envd.yaml
    api_spec: str            # path to spec/openapi.yml
    generated_docs: list[str]  # raw YAML strings from buf generate
    tmpdir: str              # temp directory (caller must not delete until done)


def docker_fetch_and_generate(envd_commit: str, api_commit: str) -> FetchedSpecs:
    """Clone e2b-dev/infra at specified commits, run buf generate, return paths.

    Uses a single Docker container that:
    1. Clones the repo at the envd commit
    2. Copies envd spec files to /output/envd/
    3. Runs buf generate on the proto files
    4. If api_commit differs, checks out that commit
    5. Copies spec/openapi.yml to /output/api/
    """
    print(f"==> Fetching specs from e2b-dev/infra")
    print(f"    envd commit: {envd_commit}")
    print(f"    api commit:  {api_commit}")

    tmpdir = tempfile.mkdtemp(prefix="e2b-openapi-")
    output_dir = tmpdir

    # Create output subdirectories
    for subdir in ("envd", "api", "generated"):
        os.makedirs(os.path.join(output_dir, subdir), exist_ok=True)

    # Build the shell script that runs inside Docker
    # It handles both commits in a single clone
    same_commit = envd_commit == api_commit
    if same_commit:
        docker_script = f"""
set -e
echo "--- Cloning e2b-dev/infra at {envd_commit} ---"
git clone --depth 1 --branch {envd_commit} {INFRA_REPO} /repo 2>/dev/null || {{
    git clone {INFRA_REPO} /repo
    cd /repo
    git checkout {envd_commit}
}}
cd /repo

echo "--- Copying envd specs ---"
cp -r {INFRA_ENVD_SPEC_DIR}/. /output/envd/

echo "--- Copying platform API spec ---"
cp {INFRA_API_SPEC} /output/api/openapi.yml

echo "--- Running buf generate ---"
cd {INFRA_ENVD_SPEC_DIR}
buf generate --template /config/buf.gen.yaml

echo "--- Done ---"
"""
    else:
        docker_script = f"""
set -e
echo "--- Cloning e2b-dev/infra ---"
git clone {INFRA_REPO} /repo
cd /repo

echo "--- Checking out envd commit: {envd_commit} ---"
git checkout {envd_commit}

echo "--- Copying envd specs ---"
cp -r {INFRA_ENVD_SPEC_DIR}/. /output/envd/

echo "--- Running buf generate ---"
cd {INFRA_ENVD_SPEC_DIR}
buf generate --template /config/buf.gen.yaml
cd /repo

echo "--- Checking out api commit: {api_commit} ---"
git checkout {api_commit}

echo "--- Copying platform API spec ---"
cp {INFRA_API_SPEC} /output/api/openapi.yml

echo "--- Done ---"
"""

    # Write buf.gen.yaml config
    buf_gen_path = os.path.join(tmpdir, "buf.gen.yaml")
    with open(buf_gen_path, "w") as f:
        f.write(BUF_GEN_YAML)

    # Write the script to a file
    script_path = os.path.join(tmpdir, "run.sh")
    with open(script_path, "w") as f:
        f.write(docker_script)

    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{output_dir}:/output",
            "-v", f"{buf_gen_path}:/config/buf.gen.yaml:ro",
            "-v", f"{script_path}:/run.sh:ro",
            DOCKER_IMAGE,
            "sh", "/run.sh",
        ],
        check=True,
    )

    # Read generated OpenAPI YAML files
    generated_dir = os.path.join(output_dir, "generated")
    generated_docs: list[str] = []
    for root, _, files in os.walk(generated_dir):
        for name in sorted(files):
            if name.endswith((".yaml", ".yml")):
                path = os.path.join(root, name)
                rel = os.path.relpath(path, generated_dir)
                print(f"    Generated: {rel}")
                with open(path) as f:
                    generated_docs.append(f.read())

    if not generated_docs:
        print("ERROR: No files were generated by buf", file=sys.stderr)
        sys.exit(1)

    envd_spec_dir = os.path.join(output_dir, "envd")
    envd_rest_spec = os.path.join(envd_spec_dir, "envd.yaml")
    api_spec = os.path.join(output_dir, "api", "openapi.yml")

    # Verify required files exist
    for path, label in [(envd_rest_spec, "envd.yaml"), (api_spec, "openapi.yml")]:
        if not os.path.exists(path):
            print(f"ERROR: {label} not found at {path}", file=sys.stderr)
            sys.exit(1)

    return FetchedSpecs(
        envd_spec_dir=envd_spec_dir,
        envd_rest_spec=envd_rest_spec,
        api_spec=api_spec,
        generated_docs=generated_docs,
        tmpdir=tmpdir,
    )


# ---------------------------------------------------------------------------
# OpenAPI merging & post-processing
# ---------------------------------------------------------------------------

def load_yaml_file(path: str) -> str:
    """Load a YAML file and return its raw content."""
    print(f"==> Loading spec: {os.path.basename(path)}")
    with open(path) as f:
        return f.read()


def merge_specs(raw_docs: list[str], protected_paths: set[str] | None = None) -> dict[str, Any]:
    """Merge multiple raw YAML OpenAPI docs into a single spec.

    Args:
        raw_docs: Raw YAML strings to merge (order matters — later docs
                  overwrite earlier ones for paths and component entries).
        protected_paths: Paths that should not be overwritten once set.
                         Used to prevent the platform API from overwriting
                         envd paths that share the same name (e.g. /health).
    """
    merged: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "E2B API",
            "version": "0.1.0",
            "description": (
                "Complete E2B developer API. "
                "Platform endpoints are served on api.e2b.app. "
                "Sandbox endpoints (envd) are served on {port}-{sandboxID}.e2b.app."
            ),
        },
        "servers": [PLATFORM_SERVER],
        "paths": {},
        "components": {},
    }

    for raw in raw_docs:
        doc = yaml.safe_load(raw)
        if not doc:
            continue

        for path, methods in doc.get("paths", {}).items():
            if protected_paths and path in protected_paths and path in merged["paths"]:
                continue
            merged["paths"][path] = methods

        for section, entries in doc.get("components", {}).items():
            if isinstance(entries, dict):
                merged["components"].setdefault(section, {}).update(entries)

        if "tags" in doc:
            merged.setdefault("tags", []).extend(doc["tags"])

        if "security" in doc:
            existing = merged.setdefault("security", [])
            for entry in doc["security"]:
                if entry not in existing:
                    existing.append(entry)

    return merged


def tag_paths_with_server(
    spec: dict[str, Any],
    paths: set[str],
    server: dict[str, Any],
) -> None:
    """Attach a specific server override to a set of paths.

    OpenAPI 3.1 allows per-path server overrides so clients know which
    base URL to use for each endpoint.
    """
    for path, path_item in spec["paths"].items():
        if path in paths:
            path_item["servers"] = [server]


def fill_streaming_endpoints(spec: dict[str, Any], streaming_rpcs: list[RpcMethod]) -> None:
    """Replace empty {} streaming path items with proper OpenAPI definitions.

    protoc-gen-connect-openapi emits {} for streaming RPCs because OpenAPI
    has no native streaming representation. We detect these from the proto
    files and fill them in with proper request/response schemas.
    """
    for rpc in streaming_rpcs:
        if rpc.path in spec["paths"]:
            print(f"    Filling streaming endpoint: {rpc.path} ({rpc.streaming_label})")
            spec["paths"][rpc.path] = build_streaming_path(rpc)


# Endpoints that don't require access token auth (matched as "METHOD/path")
AUTH_EXEMPT_ENDPOINTS = {
    "get/health",
}


def apply_sandbox_auth(spec: dict[str, Any], envd_paths: set[str]) -> None:
    """Ensure all envd/sandbox endpoints declare the SandboxAccessTokenAuth security.

    The hand-written envd.yaml already has security declarations, but the
    proto-generated Connect RPC endpoints don't. Endpoints listed in
    AUTH_EXEMPT_ENDPOINTS are left without auth requirements.
    """
    auth_security = [{SANDBOX_AUTH_SCHEME: []}]
    for path in envd_paths:
        path_item = spec["paths"].get(path)
        if not path_item:
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not op:
                continue
            key = f"{method}{path}"
            if key in AUTH_EXEMPT_ENDPOINTS:
                op.pop("security", None)
            else:
                op["security"] = auth_security


def fix_security_schemes(spec: dict[str, Any]) -> None:
    """Fix invalid apiKey securityScheme syntax.

    The source envd.yaml uses `scheme: header` which is wrong for
    type: apiKey — OpenAPI requires `in: header` instead.
    """
    for scheme in spec.get("components", {}).get("securitySchemes", {}).values():
        if scheme.get("type") == "apiKey" and "scheme" in scheme:
            scheme["in"] = scheme.pop("scheme")


def setup_sandbox_auth_scheme(spec: dict[str, Any]) -> None:
    """Define the SandboxAccessTokenAuth security scheme.

    Sandbox endpoints use X-Access-Token header (apiKey type),
    not Bearer auth. The envd.yaml source defines an AccessTokenAuth
    scheme that conflicts with the platform's AccessTokenAuth
    (Authorization: Bearer), so we replace the envd one and keep
    the platform one intact.
    """
    schemes = spec.setdefault("components", {}).setdefault("securitySchemes", {})
    # The platform API's AccessTokenAuth is Authorization: Bearer.
    # Ensure it is correctly defined (the source spec may already have it).
    schemes["AccessTokenAuth"] = {
        "type": "http",
        "scheme": "bearer",
    }
    # Define the sandbox-specific scheme
    schemes[SANDBOX_AUTH_SCHEME] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Access-Token",
        "description": (
            "Sandbox access token (`envdAccessToken`) for authenticating requests to a running sandbox. "
            "Returned by: "
            "[POST /sandboxes](/docs/api-reference/sandboxes/create-a-sandbox) (on create), "
            "[POST /sandboxes/{sandboxID}/connect](/docs/api-reference/sandboxes/connect-to-a-sandbox) (on connect), "
            "[POST /sandboxes/{sandboxID}/resume](/docs/api-reference/sandboxes/resume-a-sandbox) (on resume), "
            "and [GET /sandboxes/{sandboxID}](/docs/api-reference/sandboxes/get-a-sandbox) (for running or paused sandboxes)."
        ),
    }


# Mapping of (path, method) to desired operationId for the public docs.
# These are added at post-processing time to avoid breaking Go code generation
# (oapi-codegen derives type names from operationIds).
ENVD_OPERATION_IDS: dict[tuple[str, str], str] = {
    ("/health", "get"): "getHealth",
    ("/metrics", "get"): "getMetrics",
    ("/init", "post"): "initSandbox",
    ("/envs", "get"): "getEnvVars",
    ("/files", "get"): "downloadFile",
    ("/files", "post"): "uploadFile",
}


def add_operation_ids(spec: dict[str, Any]) -> None:
    """Add operationIds to envd endpoints for clean documentation.

    These are added at post-processing time (not in the source spec) to
    avoid changing generated Go type names.
    """
    count = 0
    for (path, method), op_id in ENVD_OPERATION_IDS.items():
        path_item = spec.get("paths", {}).get(path)
        if not path_item:
            continue
        op = path_item.get(method)
        if op and "operationId" not in op:
            op["operationId"] = op_id
            count += 1
    if count:
        print(f"==> Added {count} operationIds to envd endpoints")


STREAMING_ENDPOINTS = {
    "/filesystem.Filesystem/WatchDir",
    "/process.Process/Start",
    "/process.Process/Connect",
    "/process.Process/StreamInput",
}


def fix_spec_issues(spec: dict[str, Any]) -> None:
    """Fix known discrepancies between the source spec and the live API.

    These are upstream spec issues that we patch during post-processing
    so the published docs match actual API behavior.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    paths = spec.get("paths", {})
    fixes = []

    # 1. TemplateBuildStatus enum missing 'uploaded'
    build_status = schemas.get("TemplateBuildStatus")
    if build_status and "uploaded" not in build_status.get("enum", []):
        build_status["enum"].append("uploaded")
        fixes.append("TemplateBuildStatus: added 'uploaded' to enum")

    # 2. volumeMounts required but API doesn't always return it
    for name in ("SandboxDetail", "ListedSandbox"):
        schema = schemas.get(name, {})
        req = schema.get("required", [])
        if "volumeMounts" in req:
            req.remove("volumeMounts")
            fixes.append(f"{name}: made 'volumeMounts' optional")

    # 3. LogLevel enum too strict — server returns empty/whitespace values
    log_level = schemas.get("LogLevel")
    if log_level:
        if "enum" in log_level:
            del log_level["enum"]
        log_level["description"] = "Severity level for log entries (e.g. info, warn, error)"
        fixes.append("LogLevel: removed enum constraint, fixed description")

    # 4. Metrics schema: add missing fields and set format: int64 on byte/MiB fields
    metrics = schemas.get("Metrics")
    if metrics and "properties" in metrics:
        props = metrics["properties"]
        if "mem_used_mib" not in props:
            props["mem_used_mib"] = {
                "type": "integer",
                "description": "Used virtual memory in MiB",
            }
            fixes.append("Metrics: added 'mem_used_mib'")
        if "mem_total_mib" not in props:
            props["mem_total_mib"] = {
                "type": "integer",
                "description": "Total virtual memory in MiB",
            }
            fixes.append("Metrics: added 'mem_total_mib'")
        # Byte and MiB values can exceed int32 — set format: int64
        int64_fields = ("mem_total", "mem_used", "disk_used", "disk_total",
                        "mem_used_mib", "mem_total_mib")
        for field in int64_fields:
            if field in props and props[field].get("format") != "int64":
                props[field]["format"] = "int64"
        fixes.append("Metrics: set format int64 on memory/disk fields")

    # 5. Streaming RPC endpoints: wrong content-type and missing headers
    #    Server requires application/connect+json with envelope framing,
    #    not application/json.
    connect_version_param = {
        "name": "Connect-Protocol-Version",
        "in": "header",
        "required": True,
        "schema": {"$ref": "#/components/schemas/connect-protocol-version"},
    }
    connect_timeout_param = {
        "name": "Connect-Timeout-Ms",
        "in": "header",
        "schema": {"$ref": "#/components/schemas/connect-timeout-header"},
    }
    for ep_path in STREAMING_ENDPOINTS:
        path_item = paths.get(ep_path, {})
        op = path_item.get("post")
        if not op:
            continue
        # Fix request content-type
        rb = op.get("requestBody", {}).get("content", {})
        if "application/json" in rb and "application/connect+json" not in rb:
            rb["application/connect+json"] = rb.pop("application/json")
        # Fix response content-type
        for status_code, resp in op.get("responses", {}).items():
            if not isinstance(resp, dict):
                continue
            rc = resp.get("content", {})
            if "application/json" in rc and "application/connect+json" not in rc:
                rc["application/connect+json"] = rc.pop("application/json")
        # Add Connect-Protocol-Version and Connect-Timeout-Ms headers
        params = op.setdefault("parameters", [])
        has_cpv = any(p.get("name") == "Connect-Protocol-Version" for p in params)
        if not has_cpv:
            params.insert(0, connect_version_param)
            params.insert(1, connect_timeout_param)
        fixes.append(f"{ep_path}: content-type → application/connect+json, added Connect headers")

    # 6. EndEvent.exitCode not populated — API returns status string instead
    end_event = schemas.get("process.ProcessEvent.EndEvent")
    if end_event and "properties" in end_event:
        ec = end_event["properties"].get("exitCode")
        if ec:
            ec["deprecated"] = True
            ec["description"] = (
                "Deprecated: not populated by the server. "
                "Parse the exit code from the `status` string (e.g. \"exit status 0\")."
            )
        st = end_event["properties"].get("status")
        if st and not st.get("description"):
            st["description"] = (
                "Process exit status string (e.g. \"exit status 0\"). "
                "Parse the integer exit code from this field."
            )
        fixes.append("EndEvent: marked exitCode as deprecated, documented status string")

    # 7. envdAccessToken description misleading — only returned when secure: true
    for schema_name in ("Sandbox", "SandboxDetail"):
        schema = schemas.get(schema_name, {})
        eat = schema.get("properties", {}).get("envdAccessToken")
        if eat:
            eat["nullable"] = True
            eat["description"] = (
                "Access token for authenticating envd requests to this sandbox. "
                "Only returned when the sandbox is created with `secure: true`. "
                "Null for non-secure sandboxes (envd endpoints work without auth)."
            )
    fixes.append("envdAccessToken: clarified secure-only behavior, marked nullable")

    # 8. Sandbox.domain always null — mark as deprecated
    for schema_name in ("Sandbox", "SandboxDetail"):
        schema = schemas.get(schema_name, {})
        dom = schema.get("properties", {}).get("domain")
        if dom:
            dom["deprecated"] = True
            dom["description"] = (
                "Deprecated: always null. Construct sandbox URLs as "
                "`https://{port}-{sandboxID}.e2b.app`."
            )
    fixes.append("Sandbox.domain: marked as deprecated (always null)")

    # 9. GET /templates/{templateID}/files/{hash} returns 201, not 200
    files_path = paths.get("/templates/{templateID}/files/{hash}", {})
    files_get = files_path.get("get")
    if files_get:
        responses = files_get.get("responses", {})
        if "201" in responses and "200" not in responses:
            responses["200"] = responses.pop("201")
            responses["200"]["description"] = "Upload link for the tar file containing build layer files"
            fixes.append("/templates/{templateID}/files/{hash}: changed 201 → 200 response")

    # 10. Generate operationId for platform endpoints that lack one
    def _singularize(word: str) -> str:
        """Simple singularization for common API resource names."""
        irregulars = {"aliases": "alias", "statuses": "status", "indices": "index"}
        if word in irregulars:
            return irregulars[word]
        if word.endswith("sses"):
            return word  # "addresses" etc — skip
        if word.endswith("ies"):
            return word[:-3] + "y"
        if word.endswith("ses") or word.endswith("xes") or word.endswith("zes"):
            return word[:-2]
        if word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    op_id_count = 0
    seen_ids: dict[str, str] = {}  # operationId → path (for dedup)
    for ep_path, path_item in paths.items():
        # Skip envd endpoints (already have operationIds)
        if "/" in ep_path.lstrip("/") and "." in ep_path.split("/")[1]:
            continue
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if not op or op.get("operationId"):
                continue
            # Build operationId from method + path segments
            # Include path params to distinguish e.g. /sandboxes vs /sandboxes/{sandboxID}
            # e.g. GET /sandboxes/{sandboxID}/logs → getSandboxLogs
            # e.g. GET /v2/sandboxes → listSandboxesV2
            raw_segments = ep_path.strip("/").split("/")
            version_suffix = ""
            parts = []
            i = 0
            while i < len(raw_segments):
                seg = raw_segments[i]
                if seg in ("v2", "v3"):
                    version_suffix = seg.upper()
                    i += 1
                    continue
                if seg.startswith("{") and seg.endswith("}"):
                    # Path param — singularize the previous part if it was a collection
                    if parts:
                        parts[-1] = _singularize(parts[-1])
                    i += 1
                    continue
                parts.append(seg)
                i += 1

            # For top-level list endpoints (GET /sandboxes, GET /templates),
            # use "list" prefix instead of "get" to distinguish from single-resource GETs
            prefix = method
            if method == "get" and parts and not any(
                s.startswith("{") for s in raw_segments[1:]
            ):
                # No path params → it's a list/collection endpoint
                # But only if the last segment is plural (a collection name)
                last = parts[-1] if parts else ""
                if last.endswith("s") and last != "status":
                    prefix = "list"

            name = "".join(p.capitalize() for p in parts)
            op_id = f"{prefix}{name}{version_suffix}"

            # Dedup: if collision, append a disambiguator
            if op_id in seen_ids:
                # Try adding "ById" for single-resource variants
                if any(s.startswith("{") for s in raw_segments):
                    op_id = f"{method}{name}ById{version_suffix}"
                if op_id in seen_ids:
                    op_id = f"{method}{name}{version_suffix}_{len(seen_ids)}"

            seen_ids[op_id] = ep_path
            op["operationId"] = op_id
            op_id_count += 1
    if op_id_count:
        fixes.append(f"Generated operationId for {op_id_count} platform endpoints")

    # 11. Phantom deprecation reference: /v2/sandboxes/{sandboxID}/logs doesn't exist
    logs_path = paths.get("/sandboxes/{sandboxID}/logs", {})
    logs_get = logs_path.get("get")
    if logs_get and "/v2/" in logs_get.get("description", ""):
        logs_get["description"] = "Get sandbox logs."
        fixes.append("/sandboxes/{sandboxID}/logs: removed phantom /v2 deprecation reference")

    # 12. Truncated parameter descriptions on metrics endpoints
    metrics_desc_suffix = " are returned."
    for ep_path in paths:
        for method in ("get", "post"):
            op = (paths[ep_path] or {}).get(method)
            if not op:
                continue
            for param in op.get("parameters", []):
                if not isinstance(param, dict) or param.get("name") not in ("start", "end"):
                    continue
                # Description could be on param or nested in schema
                for target in (param, param.get("schema", {})):
                    desc = target.get("description", "")
                    if desc and desc.rstrip().endswith("the metrics"):
                        target["description"] = desc.rstrip() + metrics_desc_suffix
                        fixes.append(f"{ep_path}: completed truncated '{param['name']}' description")

    # 13. sandboxId → sandboxID casing in 502 error schema
    #     The 502 response defined on /health uses "sandboxId" (lowercase d)
    health_path = paths.get("/health", {})
    health_get = health_path.get("get")
    if health_get:
        for status_code, resp in health_get.get("responses", {}).items():
            if not isinstance(resp, dict):
                continue
            for ct, media in resp.get("content", {}).items():
                schema = media.get("schema", {})
                props = schema.get("properties", {})
                if "sandboxId" in props and "sandboxID" not in props:
                    props["sandboxID"] = props.pop("sandboxId")
                    req = schema.get("required", [])
                    for i, r in enumerate(req):
                        if r == "sandboxId":
                            req[i] = "sandboxID"
                    fixes.append("502 error schema: sandboxId → sandboxID")

    # 14. /health missing security: [] and tags
    if health_get:
        if "security" not in health_get:
            health_get["security"] = []
            fixes.append("/health: added security: [] (explicitly no auth)")
        if "tags" not in health_get:
            health_get["tags"] = ["health"]
            fixes.append("/health: added 'health' tag")

    # 15. /files responses: inline $ref responses so Mintlify renders them correctly
    #     The upstream spec uses YAML anchors that cause issues, and some renderers
    #     don't resolve response-level $refs properly.
    comp_responses = spec.get("components", {}).get("responses", {})
    files_path = paths.get("/files", {})
    for method in ("get", "post"):
        op = files_path.get(method)
        if not op:
            continue
        responses = op.get("responses", {})
        for status_code, resp in list(responses.items()):
            if not isinstance(resp, dict):
                continue
            # Inline any $ref to components/responses
            ref = resp.get("$ref", "")
            if ref.startswith("#/components/responses/"):
                ref_name = ref.split("/")[-1]
                resolved = comp_responses.get(ref_name)
                if resolved:
                    # Replace with a copy so we don't mutate the shared component
                    responses[status_code] = copy.deepcopy(resolved)
            # Also clean up any anchor-overlaid empty content
            elif "$ref" not in resp and "content" in resp:
                content = resp["content"]
                for ct, media in list(content.items()):
                    s = media.get("schema", {})
                    if s.get("description") == "Empty response":
                        del content[ct]
                if not content:
                    del resp["content"]
    fixes.append("/files: inlined response definitions for GET and POST")

    # 16. Missing type: object on schemas that have properties
    obj_fixed = 0
    for schema_name, schema in schemas.items():
        if "properties" in schema and "type" not in schema and "allOf" not in schema and "oneOf" not in schema:
            schema["type"] = "object"
            obj_fixed += 1
    if obj_fixed:
        fixes.append(f"Added type: object to {obj_fixed} schemas")

    # 17. end parameter nesting: description inside schema instead of sibling
    for ep_path in paths:
        for method in ("get", "post"):
            op = (paths[ep_path] or {}).get(method)
            if not op:
                continue
            for param in op.get("parameters", []):
                if not isinstance(param, dict) or param.get("name") != "end":
                    continue
                schema = param.get("schema", {})
                if "description" in schema and "description" not in param:
                    param["description"] = schema.pop("description")
                    fixes.append(f"{ep_path}: moved 'end' description out of schema")

    # 18. EntryInfo.type enum incomplete — missing "directory"
    entry_info = schemas.get("EntryInfo")
    if entry_info:
        type_prop = entry_info.get("properties", {}).get("type")
        if type_prop and type_prop.get("enum") == ["file"]:
            type_prop["enum"] = ["file", "directory"]
            fixes.append("EntryInfo.type: added 'directory' to enum")

    # 19. SandboxMetadata and EnvVars lack type: object
    for name in ("SandboxMetadata", "EnvVars"):
        schema = schemas.get(name, {})
        if "additionalProperties" in schema and "type" not in schema:
            schema["type"] = "object"
            fixes.append(f"{name}: added type: object")

    # 20. TemplateLegacy missing 'names' and 'buildStatus' fields
    tpl_legacy = schemas.get("TemplateLegacy")
    if tpl_legacy and "properties" in tpl_legacy:
        props = tpl_legacy["properties"]
        if "names" not in props:
            props["names"] = {
                "type": "array",
                "description": "Names of the template (namespace/alias format when namespaced)",
                "items": {"type": "string"},
            }
            fixes.append("TemplateLegacy: added 'names' property")
        if "buildStatus" not in props:
            props["buildStatus"] = {"$ref": "#/components/schemas/TemplateBuildStatus"}
            fixes.append("TemplateLegacy: added 'buildStatus' property")

    # 21. connect-protocol-version: redundant enum + const
    cpv = schemas.get("connect-protocol-version")
    if cpv and "enum" in cpv and "const" in cpv:
        del cpv["enum"]
        fixes.append("connect-protocol-version: removed redundant enum (const is sufficient)")

    # 22. filesystem.EntryInfo.size union type undocumented
    fs_entry = schemas.get("filesystem.EntryInfo")
    if fs_entry and "properties" in fs_entry:
        size_prop = fs_entry["properties"].get("size")
        if size_prop and isinstance(size_prop.get("type"), list):
            size_prop["description"] = (
                "File size in bytes. Encoded as string for values exceeding "
                "JSON number precision (int64)."
            )
            fixes.append("filesystem.EntryInfo.size: documented integer/string union type")

    # 23. GET /health 502 uses application/connect+json — change to application/json
    if health_get:
        for status_code, resp in health_get.get("responses", {}).items():
            if not isinstance(resp, dict):
                continue
            content = resp.get("content", {})
            if "application/connect+json" in content and "application/json" not in content:
                content["application/json"] = content.pop("application/connect+json")
                fixes.append(f"/health {status_code}: content-type → application/json")

    # 24. PATCH /templates/{templateID} (deprecated) returns empty object —
    #     use TemplateUpdateResponse like v2
    patch_v1_path = paths.get("/templates/{templateID}", {})
    patch_v1 = patch_v1_path.get("patch")
    if patch_v1:
        resp_200 = patch_v1.get("responses", {}).get("200", {})
        # Replace the entire content dict (don't modify shared YAML anchor object)
        resp_200["content"] = {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/TemplateUpdateResponse"}
            }
        }
        fixes.append("PATCH /templates/{templateID}: response → TemplateUpdateResponse")

    # 25. POST /sandboxes/{sandboxID}/refreshes missing 500 response
    refreshes_path = paths.get("/sandboxes/{sandboxID}/refreshes", {})
    refreshes_post = refreshes_path.get("post")
    if refreshes_post:
        responses = refreshes_post.get("responses", {})
        if "500" not in responses:
            responses["500"] = {"$ref": "#/components/responses/500"}
            fixes.append("/sandboxes/{sandboxID}/refreshes: added 500 response")

    # 25. Add short summary fields to platform endpoints for Mintlify sidebar names
    SUMMARIES: dict[tuple[str, str], str] = {
        # Sandboxes
        ("/sandboxes", "get"): "List sandboxes",
        ("/sandboxes", "post"): "Create sandbox",
        ("/v2/sandboxes", "get"): "List sandboxes (v2)",
        ("/sandboxes/metrics", "get"): "List sandbox metrics",
        ("/sandboxes/{sandboxID}/logs", "get"): "Get sandbox logs",
        ("/sandboxes/{sandboxID}", "get"): "Get sandbox",
        ("/sandboxes/{sandboxID}", "delete"): "Delete sandbox",
        ("/sandboxes/{sandboxID}/metrics", "get"): "Get sandbox metrics",
        ("/sandboxes/{sandboxID}/pause", "post"): "Pause sandbox",
        ("/sandboxes/{sandboxID}/resume", "post"): "Resume sandbox",
        ("/sandboxes/{sandboxID}/connect", "post"): "Connect to sandbox",
        ("/sandboxes/{sandboxID}/timeout", "post"): "Set sandbox timeout",
        ("/sandboxes/{sandboxID}/refreshes", "post"): "Refresh sandbox",
        # Templates
        ("/v3/templates", "post"): "Create template (v3)",
        ("/v2/templates", "post"): "Create template (v2)",
        ("/templates/{templateID}/files/{hash}", "get"): "Get build upload link",
        ("/templates", "get"): "List templates",
        ("/templates", "post"): "Create template",
        ("/templates/{templateID}", "get"): "Get template",
        ("/templates/{templateID}", "post"): "Rebuild template",
        ("/templates/{templateID}", "delete"): "Delete template",
        ("/templates/{templateID}", "patch"): "Update template",
        ("/templates/{templateID}/builds/{buildID}", "post"): "Start build",
        ("/v2/templates/{templateID}/builds/{buildID}", "post"): "Start build (v2)",
        ("/v2/templates/{templateID}", "patch"): "Update template (v2)",
        ("/templates/{templateID}/builds/{buildID}/status", "get"): "Get build status",
        ("/templates/{templateID}/builds/{buildID}/logs", "get"): "Get build logs",
        ("/templates/aliases/{alias}", "get"): "Get template by alias",
        # Tags
        ("/templates/tags", "post"): "Assign tags",
        ("/templates/tags", "delete"): "Delete tags",
        ("/templates/{templateID}/tags", "get"): "List template tags",
        # Teams
        ("/teams", "get"): "List teams",
        ("/teams/{teamID}/metrics", "get"): "Get team metrics",
        ("/teams/{teamID}/metrics/max", "get"): "Get team metrics max",
    }
    summary_count = 0
    for (path_str, method), summary in SUMMARIES.items():
        op = paths.get(path_str, {}).get(method)
        if op:
            op["summary"] = summary
            summary_count += 1
    if summary_count:
        fixes.append(f"Added summary to {summary_count} platform endpoints")

    # 27. Replace nullable: true with OpenAPI 3.1.0 type arrays
    #     In 3.1.0, nullable was removed. Use type: ["string", "null"] instead,
    #     or oneOf with type: 'null' for $ref properties.
    nullable_fixed = 0
    for schema_name, schema in schemas.items():
        if "properties" not in schema:
            continue
        for prop_name, prop in schema["properties"].items():
            if not isinstance(prop, dict) or not prop.pop("nullable", False):
                continue
            # allOf + nullable → oneOf: [allOf[...], type: 'null']
            if "allOf" in prop:
                all_of = prop.pop("allOf")
                prop["oneOf"] = all_of + [{"type": "null"}]
            # plain type + nullable → type: [original, "null"]
            elif "type" in prop:
                orig_type = prop["type"]
                if isinstance(orig_type, list):
                    if "null" not in orig_type:
                        orig_type.append("null")
                else:
                    prop["type"] = [orig_type, "null"]
            # $ref + nullable → oneOf: [$ref, type: 'null']
            elif "$ref" in prop:
                ref = prop.pop("$ref")
                prop["oneOf"] = [{"$ref": ref}, {"type": "null"}]
            # additionalProperties + nullable (e.g. McpConfig)
            elif "additionalProperties" in prop:
                prop["type"] = ["object", "null"]
            nullable_fixed += 1
    if nullable_fixed:
        fixes.append(f"Replaced nullable: true with 3.1.0 type arrays on {nullable_fixed} properties")

    if fixes:
        print(f"==> Fixed {len(fixes)} spec issues:")
        for f in fixes:
            print(f"    {f}")


def _strip_supabase_security(path_item: dict[str, Any]) -> None:
    """Remove Supabase security entries from all operations in a path item.

    Each operation's security list is an OR of auth options. We remove
    any option that references a Supabase scheme, keeping the rest.
    """
    for method in ("get", "post", "put", "patch", "delete", "head", "options"):
        op = path_item.get(method)
        if not op or "security" not in op:
            continue
        op["security"] = [
            sec_req for sec_req in op["security"]
            if not any("supabase" in key.lower() for key in sec_req)
        ]


def _has_admin_token_security(path_item: dict[str, Any]) -> bool:
    """Check if any operation in a path item references AdminToken auth."""
    for method in ("get", "post", "put", "patch", "delete", "head", "options"):
        op = path_item.get(method)
        if not op:
            continue
        for sec_req in op.get("security", []):
            if any("admin" in key.lower() for key in sec_req):
                return True
    return False


def filter_paths(spec: dict[str, Any]) -> None:
    """Clean up paths that should not appear in the public spec.

    - Removes access-token and api-key endpoints
    - Removes endpoints using AdminToken auth
    - Strips Supabase auth entries from all operations
    - Removes Supabase and AdminToken securityScheme definitions
    """
    # Remove excluded paths
    excluded_prefixes = ("/access-tokens", "/api-keys", "/volumes")
    excluded_exact = {"/v2/sandboxes/{sandboxID}/logs", "/init"}
    to_remove = [
        p for p in spec["paths"]
        if p.startswith(excluded_prefixes) or p in excluded_exact
    ]

    # Remove admin-only paths
    for path, path_item in spec["paths"].items():
        if path not in to_remove and _has_admin_token_security(path_item):
            to_remove.append(path)

    for path in to_remove:
        del spec["paths"][path]
    if to_remove:
        print(f"==> Removed {len(to_remove)} paths (volumes, admin, internal)")

    # Strip supabase security entries from all operations
    for path_item in spec["paths"].values():
        _strip_supabase_security(path_item)

    # Remove supabase and admin security scheme definitions
    schemes = spec.get("components", {}).get("securitySchemes", {})
    remove_keys = [k for k in schemes if "supabase" in k.lower() or "admin" in k.lower()]
    for key in remove_keys:
        del schemes[key]
    if remove_keys:
        print(f"==> Removed {len(remove_keys)} internal security schemes")


def remove_orphaned_schemas(spec: dict[str, Any]) -> None:
    """Remove component schemas that are not referenced anywhere in the spec.
    Runs iteratively since removing schemas may orphan others."""
    all_orphaned: list[str] = []

    while True:
        spec_text = ""
        # Serialize paths + top-level refs (excluding components.schemas itself)
        for section in ("paths", "security"):
            if section in spec:
                spec_text += yaml.dump(spec[section], default_flow_style=False)
        for section, entries in spec.get("components", {}).items():
            if section != "schemas":
                spec_text += yaml.dump(entries, default_flow_style=False)
        # Also check cross-references within schemas
        schemas = spec.get("components", {}).get("schemas", {})
        schema_text = yaml.dump(schemas, default_flow_style=False)

        orphaned = []
        for name in list(schemas.keys()):
            # Use exact ref pattern to avoid substring collisions
            # (e.g. "schemas/Foo" matching inside "schemas/FooBar")
            ref_pattern = f"schemas/{name}'"
            # Referenced from paths/responses/params
            if ref_pattern in spec_text:
                continue
            # Referenced from other schemas (exclude self-definition)
            used = False
            for other_name, other_schema in schemas.items():
                if other_name == name:
                    continue
                if ref_pattern in yaml.dump(other_schema, default_flow_style=False):
                    used = True
                    break
            if not used:
                orphaned.append(name)

        if not orphaned:
            break

        for name in orphaned:
            del schemas[name]
        all_orphaned.extend(orphaned)

    if all_orphaned:
        print(f"==> Removed {len(all_orphaned)} orphaned schemas: {', '.join(sorted(all_orphaned))}")


SANDBOX_NOT_FOUND_RESPONSE = {
    "description": "Sandbox not found",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["sandboxId", "message", "code"],
                "properties": {
                    "sandboxId": {
                        "type": "string",
                        "description": "Identifier of the sandbox",
                    },
                    "message": {
                        "type": "string",
                        "description": "Error message",
                    },
                    "code": {
                        "type": "integer",
                        "description": "Error code",
                    },
                },
            }
        }
    },
}


EMPTY_RESPONSE_CONTENT = {
    "application/json": {
        "schema": {"type": "object", "description": "Empty response"}
    }
}


def add_sandbox_not_found(spec: dict[str, Any], envd_paths: set[str]) -> None:
    """Add a 502 response to all sandbox/envd endpoints.

    The load balancer returns 502 when a sandbox is not found.
    """
    count = 0
    for path in envd_paths:
        path_item = spec["paths"].get(path)
        if not path_item:
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if op and "502" not in op.get("responses", {}):
                op.setdefault("responses", {})["502"] = SANDBOX_NOT_FOUND_RESPONSE
                count += 1
    if count:
        print(f"==> Added 502 sandbox-not-found response to {count} operations")


def fill_empty_responses(spec: dict[str, Any]) -> None:
    """Add an empty content block to any 2xx response that lacks one.

    Mintlify requires a content block on every response to render correctly.
    """
    filled = 0
    stripped = 0
    for path, path_item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if not op:
                continue
            responses = op.get("responses", {})
            # Remove "default" responses (generic Connect error envelopes)
            if "default" in responses:
                del responses["default"]
                stripped += 1
            for status, resp in responses.items():
                if not isinstance(resp, dict):
                    continue
                # 204 = No Content: remove any content block
                if str(status) == "204":
                    resp.pop("content", None)
                    continue
                # Skip responses that use $ref (content comes from the referenced response)
                if "$ref" in resp:
                    continue
                if str(status).startswith("2") and "content" not in resp:
                    resp["content"] = EMPTY_RESPONSE_CONTENT
                    filled += 1
    if filled:
        print(f"==> Added empty content block to {filled} responses")
    if stripped:
        print(f"==> Removed {stripped} default error responses")


def rename_and_reorder_tags(spec: dict[str, Any]) -> None:
    """Rename tags and reorder them for the documentation sidebar."""
    TAG_RENAME = {
        "sandboxes": "Sandboxes",
        "snapshots": "Sandboxes",
        "templates": "Templates",
        "filesystem.Filesystem": "Filesystem",
        "process.Process": "Process",
        "tags": "Tags",
        "auth": "Teams",
        "health": "Others",
        "files": "Others",
    }
    TAG_ORDER = ["Sandboxes", "Templates", "Filesystem", "Process", "Tags", "Teams", "Others"]

    # Rename tags on all operations; tag untagged ones as "Others"
    for path_item in spec.get("paths", {}).values():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if not op:
                continue
            if "tags" not in op:
                op["tags"] = ["Others"]
            else:
                op["tags"] = [TAG_RENAME.get(t, t) for t in op["tags"]]

    # Rebuild the top-level tags list in the desired order
    spec["tags"] = [{"name": t} for t in TAG_ORDER]

    # Reorder paths so Mintlify renders sections in the desired order.
    # Mintlify uses path order (not the tags array) to determine sidebar order.
    tag_priority = {t: i for i, t in enumerate(TAG_ORDER)}

    def path_sort_key(item: tuple[str, dict]) -> int:
        path_str, path_item = item
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if op and "tags" in op:
                return tag_priority.get(op["tags"][0], len(TAG_ORDER))
        return len(TAG_ORDER)

    spec["paths"] = dict(sorted(spec["paths"].items(), key=path_sort_key))
    print(f"==> Renamed and reordered {len(TAG_ORDER)} tags")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    # Parse CLI args
    envd_commit = "main"
    api_commit = "main"
    output_path = os.path.join(DOCS_REPO_ROOT, "openapi-public.yml")

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--envd-commit" and i + 1 < len(args):
            envd_commit = args[i + 1]
            i += 2
        elif args[i] == "--api-commit" and i + 1 < len(args):
            api_commit = args[i + 1]
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif args[i] in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"Unknown argument: {args[i]}", file=sys.stderr)
            print(__doc__, file=sys.stderr)
            sys.exit(2)
            i += 1

    print("=" * 60)
    print("  E2B OpenAPI Reference Generator")
    print("=" * 60)
    print(f"  Source repo:    {INFRA_REPO}")
    print(f"  envd commit:    {envd_commit}")
    print(f"  api commit:     {api_commit}")
    print(f"  Output:         {output_path}")
    print()

    # Build Docker image
    docker_build_image()

    # Fetch specs and generate proto OpenAPI
    specs = docker_fetch_and_generate(envd_commit, api_commit)

    try:
        # --- Sandbox API (envd) ---
        envd_rest_doc = load_yaml_file(specs.envd_rest_spec)
        proto_docs = specs.generated_docs

        # Track which paths come from envd so we can set their server
        envd_raw_docs = [envd_rest_doc] + proto_docs
        envd_paths: set[str] = set()
        for raw in envd_raw_docs:
            doc = yaml.safe_load(raw)
            if doc and "paths" in doc:
                envd_paths.update(doc["paths"].keys())

        # --- Platform API ---
        api_doc = load_yaml_file(specs.api_spec)

        # --- Merge everything ---
        # Order: envd first, then platform API (platform schemas take precedence
        # for shared names like Error since they're more complete).
        # Protect envd paths so the platform API doesn't overwrite them
        # (e.g. /health exists in both but the envd version is authoritative).
        merged = merge_specs(envd_raw_docs + [api_doc], protected_paths=envd_paths)

        # Auto-detect and fill streaming RPC endpoints
        streaming_rpcs = find_streaming_rpcs(specs.envd_spec_dir)
        print(f"==> Found {len(streaming_rpcs)} streaming RPCs in proto files")
        fill_streaming_endpoints(merged, streaming_rpcs)
        for rpc in streaming_rpcs:
            envd_paths.add(rpc.path)

        # Attach per-path server overrides so each path has exactly one server
        tag_paths_with_server(merged, envd_paths, SANDBOX_SERVER)
        platform_paths = set(merged["paths"].keys()) - envd_paths
        tag_paths_with_server(merged, platform_paths, PLATFORM_SERVER)

        # Ensure all sandbox endpoints declare auth
        apply_sandbox_auth(merged, envd_paths)

        # Add 502 sandbox-not-found to all envd endpoints
        add_sandbox_not_found(merged, envd_paths)

        # Fix known issues
        fix_security_schemes(merged)
        setup_sandbox_auth_scheme(merged)
        add_operation_ids(merged)
        fix_spec_issues(merged)

        # Remove internal/unwanted paths
        filter_paths(merged)

        # Ensure all 2xx responses have a content block (required by Mintlify)
        fill_empty_responses(merged)

        # Clean up unreferenced schemas left over from filtered paths
        remove_orphaned_schemas(merged)

        # Rename and reorder tags for documentation sidebar
        rename_and_reorder_tags(merged)

        # Write output
        with open(output_path, "w") as f:
            yaml.dump(merged, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"\n==> Written to {output_path}")

    finally:
        # Clean up temp directory
        import shutil
        shutil.rmtree(specs.tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
