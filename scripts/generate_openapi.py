#!/usr/bin/env python3
"""
OpenAPI Spec Generation Script

Generates the public API reference by merging and polishing specs from the
local infra repository clone. Reads the REST API spec and Sandbox API spec,
filters admin/internal endpoints, applies documentation polish, and outputs
a single merged spec for Mintlify.

Usage:
    python scripts/generate_openapi.py [--infra-path /path/to/infra]

By default, looks for the infra repo at ../infra relative to this repo.
The expanded envd.yaml should include all sandbox endpoints (filesystem, process).
"""

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

# Import from our mindmap module
sys.path.insert(0, str(Path(__file__).parent))
from api_mindmap import TAGS as MINDMAP_TAGS  # noqa: E402

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INFRA_PATH = REPO_ROOT.parent / "infra"
OUTPUT_FILENAME = "openapi-public-edited.yml"

EXCLUDE_REST_PATHS = [
    "/access-tokens",
    "/access-tokens/{accessTokenID}",
    "/admin/teams/{teamID}/sandboxes/kill",
    "/api-keys",
    "/api-keys/{apiKeyID}",
    "/health",
    "/nodes",
    "/nodes/{nodeID}",
]

# Paths to include even when they don't have ApiKeyAuth in the source spec
FORCE_INCLUDE_PATHS = {
    "/teams",
    "/templates",
    "/templates/{templateID}",
    "/templates/{templateID}/builds/{buildID}",
}

EXCLUDE_SECURITY_SCHEMES = [
    "Supabase1TokenAuth",
    "Supabase2TeamAuth",
    "AdminTokenAuth",
]

# Parameters only used by admin/internal endpoints
EXCLUDE_PARAMETERS = {"nodeID", "apiKeyID", "accessTokenID", "tag"}

# Schemas only used by admin/internal endpoints
EXCLUDE_SCHEMAS = [
    "AdminSandboxKillResult",
    "CreatedAccessToken",
    "CreatedTeamAPIKey",
    "DiskMetrics",
    "IdentifierMaskingDetails",
    "MachineInfo",
    "NewAccessToken",
    "NewTeamAPIKey",
    "Node",
    "NodeDetail",
    "NodeMetrics",
    "NodeStatus",
    "NodeStatusChange",
    "TeamAPIKey",
    "UpdateTeamAPIKey",
]

SANDBOX_EXCLUDE_PATHS = ["/health", "/metrics", "/envs"]

SANDBOX_TAG_RENAMES = {
    "files": "Sandbox Filesystem",
    "filesystem": "Sandbox Filesystem",
    "process": "Sandbox Process",
}

# ---------------------------------------------------------------------------
# DOCUMENTATION POLISH — rich descriptions, summaries, operationIds, examples
# ---------------------------------------------------------------------------

INFO = {
    "version": "0.1.0",
    "title": "E2B API",
    "description": (
        "The E2B API allows you to programmatically create, manage, and interact "
        "with cloud sandboxes - secure, isolated environments for running code.\n"
        "\n"
        "## Overview\n"
        "\n"
        "The API is split into two parts:\n"
        "\n"
        "### Control Plane API (`api.e2b.app`)\n"
        "Use this API to manage the lifecycle of sandboxes and templates:\n"
        "- **Sandboxes**: Create, list, pause, resume, and terminate sandboxes\n"
        "- **Templates**: Build and manage custom sandbox templates\n"
        "- **Metrics**: Monitor usage and resource consumption\n"
        "\n"
        "### Data Plane API (`{port}-{sandboxId}.e2b.app`)\n"
        "Use this API to interact with a running sandbox:\n"
        "- **Files**: Upload and download files\n"
        "- **Filesystem**: Create directories, list contents, move and delete files\n"
        "- **Processes**: Start, monitor, and control processes\n"
        "\n"
        "## Authentication\n"
        "\n"
        "### Control Plane (X-API-Key)\n"
        "All Control Plane endpoints require your API key in the `X-API-Key` header.\n"
        "Get your API key from the [E2B Dashboard](https://e2b.dev/dashboard?tab=keys).\n"
        "\n"
        "```bash\n"
        'curl -H "X-API-Key: e2b_YOUR_API_KEY" https://api.e2b.app/sandboxes\n'
        "```\n"
        "\n"
        "### Data Plane (X-Access-Token)\n"
        "Data Plane endpoints require the `X-Access-Token` header with the access token\n"
        "returned when you create a sandbox.\n"
        "\n"
        "```bash\n"
        "# 1. Create a sandbox (returns sandboxId and envdAccessToken)\n"
        'curl -X POST -H "X-API-Key: e2b_YOUR_API_KEY" \\\n'
        "  -d '{\"templateID\": \"base\"}' \\\n"
        "  https://api.e2b.app/sandboxes\n"
        "\n"
        "# 2. Use the token to interact with the sandbox\n"
        'curl -H "X-Access-Token: YOUR_ACCESS_TOKEN" \\\n'
        "  https://49982-YOUR_SANDBOX_ID.e2b.app/files?path=/home/user/file.txt\n"
        "```\n"
        "\n"
        "## Quick Start\n"
        "\n"
        "1. **Create a sandbox** from a template using `POST /sandboxes`\n"
        "2. **Get the access token** from the response (`envdAccessToken`)\n"
        "3. **Interact with the sandbox** using the Data Plane API\n"
        "4. **Clean up** by deleting the sandbox with `DELETE /sandboxes/{sandboxID}`\n"
        "\n"
        "## Rate Limits\n"
        "\n"
        "API requests are rate limited. Contact support if you need higher limits.\n"
        "\n"
        "## SDKs\n"
        "\n"
        "We provide official SDKs for Python, JavaScript/TypeScript, and Go.\n"
        "See [SDK Reference](https://e2b.dev/docs/sdk-reference) for details."
    ),
}

# Tags — reuse from mindmap module for descriptions, keep exact same order
TAGS = [
    {"name": t["name"], "description": t["description"]}
    for t in MINDMAP_TAGS
]

# Sandbox endpoint polish (applied during sandbox processing)
SANDBOX_ENDPOINT_POLISH = {
    "POST /init": {
        "summary": "Initialize sandbox",
        "description": "Initializes a sandbox after creation. Syncs environment variables and metadata.",
        "operationId": "initSandbox",
        "tags": ["Sandboxes"],
        "addResponses": [400, 401],
    },
}

# Connect RPC error codes to add to all filesystem and process endpoints.
# Connect RPC maps its error codes to HTTP status codes:
#   InvalidArgument -> 400, Unauthenticated -> 401, NotFound -> 404,
#   AlreadyExists -> 409, Internal -> 500
CONNECT_RPC_ERRORS = {
    "/filesystem.Filesystem/": [400, 401, 404, 500],
    "/process.Process/": [400, 401, 404, 500],
}

# Additional error codes for specific sandbox HTTP endpoints
SANDBOX_HTTP_ERRORS = {
    "GET /files": [],    # already has error responses in source spec
    "POST /files": [],   # already has error responses in source spec
}

# Per-endpoint documentation polish for REST API endpoints
# Keys are "METHOD /path", values override properties on the operation
ENDPOINT_POLISH: dict[str, dict] = {
    "GET /sandboxes": {
        "summary": "List running sandboxes",
        "description": (
            "Returns a list of all currently running sandboxes for your team.\n"
            "Use the `metadata` parameter to filter sandboxes by custom metadata.\n"
            "\n"
            "**Note:** This endpoint only returns running sandboxes. Paused sandboxes\n"
            "are not included. Use `GET /v2/sandboxes` with state filter for more options."
        ),
        "operationId": "listSandboxes",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            200: {
                "description": "List of running sandboxes",
                "example": [
                    {
                        "sandboxID": "sandbox-abc123xyz",
                        "templateID": "base",
                        "alias": "my-python-env",
                        "clientID": "sandbox-abc123xyz",
                        "startedAt": "2024-01-15T10:30:00Z",
                        "endAt": "2024-01-15T10:45:00Z",
                        "cpuCount": 2,
                        "memoryMB": 512,
                        "metadata": {"user": "user-123", "project": "demo"},
                    },
                ],
            },
        },
        "paramOverrides": {
            "metadata": {
                "description": (
                    "Filter sandboxes by metadata. Format: key=value&key2=value2\n"
                    "Each key and value must be URL encoded."
                ),
                "example": "user=user-123&project=demo",
            },
        },
    },
    "POST /sandboxes": {
        "summary": "Create a sandbox",
        "description": (
            "Creates a new sandbox from the specified template. The sandbox starts\n"
            "immediately and is ready to use within a few seconds.\n"
            "\n"
            "**Returns:**\n"
            "- `sandboxID`: Use this to identify the sandbox in subsequent API calls\n"
            "- `envdAccessToken`: Use this as `X-Access-Token` for Data Plane API calls"
        ),
        "operationId": "createSandbox",
        "tags": ["Sandboxes"],
        "requestExample": {
            "templateID": "base",
            "timeout": 300,
            "metadata": {"user": "user-123", "project": "code-review"},
        },
        "responseOverrides": {
            201: {
                "description": "Sandbox created successfully",
                "example": {
                    "sandboxID": "sandbox-abc123xyz",
                    "templateID": "base",
                    "clientID": "sandbox-abc123xyz",
                    "envdAccessToken": "eyJhbGciOiJIUzI1NiIs...",
                    "envdVersion": "0.1.0",
                },
            },
        },
        "addResponses": [403, 404, 429],
    },
    "GET /sandboxes/{sandboxID}": {
        "summary": "Get sandbox details",
        "description": (
            "Returns detailed information about a specific sandbox, including its\n"
            "current state, resource allocation, and metadata."
        ),
        "operationId": "getSandbox",
        "tags": ["Sandboxes"],
        "addResponses": [403],
    },
    "DELETE /sandboxes/{sandboxID}": {
        "summary": "Terminate a sandbox",
        "description": (
            "Immediately terminates and deletes a sandbox. All data in the sandbox\n"
            "is permanently lost.\n"
            "\n"
            "**Warning:** This action cannot be undone. If you want to preserve the\n"
            "sandbox state for later, use `POST /sandboxes/{sandboxID}/pause` instead."
        ),
        "operationId": "deleteSandbox",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            204: {"description": "Sandbox terminated successfully"},
        },
        "addResponses": [403],
    },
    "POST /sandboxes/{sandboxID}/pause": {
        "summary": "Pause a sandbox",
        "description": (
            "Pauses a running sandbox. The sandbox state is preserved and can be\n"
            "resumed later with `POST /sandboxes/{sandboxID}/connect`.\n"
            "\n"
            "**Benefits of pausing:**\n"
            "- No compute charges while paused\n"
            "- State is preserved (files, installed packages, etc.)\n"
            "- Resume in seconds instead of creating a new sandbox\n"
            "\n"
            "**Limitations:**\n"
            "- Running processes are stopped\n"
            "- Network connections are closed\n"
            "- Paused sandboxes have a maximum retention period"
        ),
        "operationId": "pauseSandbox",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            204: {"description": "Sandbox paused successfully"},
        },
        "addResponses": [400, 403],
    },
    "POST /sandboxes/{sandboxID}/resume": {
        "summary": "Resume a paused sandbox",
        "description": (
            "Resumes a previously paused sandbox.\n"
            "\n"
            "**Deprecated:** Use `POST /sandboxes/{sandboxID}/connect` instead,\n"
            "which handles both running and paused sandboxes."
        ),
        "operationId": "resumeSandbox",
        "tags": ["Sandboxes"],
        "addResponses": [400, 403, 429],
    },
    "POST /sandboxes/{sandboxID}/connect": {
        "summary": "Connect to or resume a sandbox",
        "description": (
            "Returns sandbox connection details. If the sandbox is paused, it will\n"
            "be automatically resumed.\n"
            "\n"
            "Use this endpoint to:\n"
            "- Resume a paused sandbox\n"
            "- Get connection details for a running sandbox\n"
            "- Extend the sandbox timeout\n"
            "\n"
            "**Note:** The timeout is extended from the current time, not added to\n"
            "the existing timeout."
        ),
        "operationId": "connectSandbox",
        "tags": ["Sandboxes"],
        "addResponses": [403, 429],
    },
    "POST /sandboxes/{sandboxID}/timeout": {
        "summary": "Set sandbox timeout",
        "description": (
            "Sets a new timeout for the sandbox. The sandbox will automatically\n"
            "terminate after the specified number of seconds from now.\n"
            "\n"
            "**Note:** This replaces any existing timeout. Each call resets the\n"
            "countdown from the current time."
        ),
        "operationId": "setSandboxTimeout",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            204: {"description": "Timeout updated successfully"},
        },
    },
    "POST /sandboxes/{sandboxID}/refreshes": {
        "summary": "Extend sandbox lifetime",
        "description": (
            "Extends the sandbox lifetime by the specified duration. Unlike\n"
            "`/timeout`, this adds time to the existing expiration."
        ),
        "operationId": "refreshSandbox",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            204: {"description": "Sandbox lifetime extended"},
        },
        "addResponses": [400, 500],
    },
    "GET /v2/sandboxes": {
        "summary": "List all sandboxes (v2)",
        "description": (
            "Returns all sandboxes, including paused ones. Supports filtering by\n"
            "state and metadata, and pagination."
        ),
        "operationId": "listSandboxesV2",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            200: {"description": "List of sandboxes"},
        },
    },
    "GET /sandboxes/metrics": {
        "summary": "Get metrics for multiple sandboxes",
        "description": (
            "Returns the latest metrics for a batch of sandboxes. Useful for\n"
            "monitoring dashboards."
        ),
        "operationId": "getSandboxesMetrics",
        "tags": ["Metrics"],
        "responseOverrides": {
            200: {"description": "Metrics per sandbox"},
        },
        "paramOverrides": {
            "sandbox_ids": {
                "description": "Comma-separated list of sandbox IDs (max 100)",
            },
        },
    },
    "GET /sandboxes/{sandboxID}/logs": {
        "summary": "Get sandbox logs (legacy)",
        "description": (
            "Returns system logs from the sandbox.\n"
            "\n"
            "**Deprecated:** Use `GET /v2/sandboxes/{sandboxID}/logs` instead."
        ),
        "operationId": "getSandboxLogs",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            200: {"description": "Sandbox logs"},
        },
        "paramOverrides": {
            "start": {"description": "Start timestamp in milliseconds (Unix epoch)"},
            "limit": {"description": "Maximum number of log entries to return"},
        },
        "addResponses": [400],
    },
    "GET /v2/sandboxes/{sandboxID}/logs": {
        "summary": "Get sandbox logs",
        "description": (
            "Returns system logs from the sandbox. These include sandbox startup logs\n"
            "and system-level events. Supports pagination and filtering."
        ),
        "operationId": "getSandboxLogsV2",
        "tags": ["Sandboxes"],
        "responseOverrides": {
            200: {"description": "Sandbox logs"},
        },
        "paramOverrides": {
            "cursor": {"description": "Starting timestamp in milliseconds (Unix epoch)"},
            "limit": {"description": "Maximum number of log entries to return"},
        },
        "addResponses": [400],
    },
    "GET /sandboxes/{sandboxID}/metrics": {
        "summary": "Get sandbox metrics",
        "description": (
            "Returns resource usage metrics (CPU, memory, disk) for a specific sandbox\n"
            "over a time range."
        ),
        "operationId": "getSandboxMetrics",
        "tags": ["Metrics"],
        "responseOverrides": {
            200: {"description": "Sandbox metrics"},
        },
        "paramOverrides": {
            "start": {"description": "Start timestamp in seconds (Unix epoch)"},
            "end": {"description": "End timestamp in seconds (Unix epoch)"},
        },
    },
    "GET /teams/{teamID}/metrics": {
        "summary": "Get team metrics",
        "description": (
            "Returns usage metrics for your team over a time range, including\n"
            "concurrent sandbox count and sandbox start rate."
        ),
        "operationId": "getTeamMetrics",
        "tags": ["Metrics"],
        "responseOverrides": {
            200: {"description": "Team metrics"},
        },
        "addResponses": [403],
    },
    "GET /teams/{teamID}/metrics/max": {
        "summary": "Get max team metrics",
        "description": (
            "Returns the maximum value of a specific metric for your team\n"
            "over a time range."
        ),
        "operationId": "getTeamMetricsMax",
        "tags": ["Metrics"],
        "responseOverrides": {
            200: {"description": "Maximum metric value"},
        },
        "paramOverrides": {
            "metric": {"description": "Which metric to get the maximum value for"},
        },
        "addResponses": [403],
    },
    "GET /teams": {
        "summary": "List teams",
        "description": "Returns all teams accessible to the authenticated user.",
        "operationId": "listTeams",
        "tags": ["Teams"],
    },
    "GET /templates": {
        "summary": "List templates",
        "description": (
            "Returns all templates accessible to your team, including both custom\n"
            "templates you've created and public templates."
        ),
        "operationId": "listTemplates",
        "tags": ["Templates"],
    },
    "POST /templates": {
        "summary": "Create a new template (legacy)",
        "description": (
            "Creates a new template from a Dockerfile.\n"
            "\n"
            "**Deprecated:** Use `POST /v3/templates` instead."
        ),
        "operationId": "createTemplateLegacy",
        "tags": ["Templates"],
        "addResponses": [403, 409, 429],
    },
    "GET /templates/{templateID}": {
        "summary": "Get template details",
        "description": "Returns detailed information about a template, including all its builds.",
        "operationId": "getTemplate",
        "tags": ["Templates"],
        "responseOverrides": {
            200: {"description": "Template details with builds"},
        },
        "addResponses": [400, 403, 404],
    },
    "POST /templates/{templateID}": {
        "summary": "Rebuild a template (legacy)",
        "description": (
            "Triggers a rebuild of an existing template from a Dockerfile.\n"
            "\n"
            "**Deprecated:** Use `POST /v3/templates` instead."
        ),
        "operationId": "rebuildTemplateLegacy",
        "tags": ["Templates"],
        "addResponses": [403, 404, 409, 429],
    },
    "DELETE /templates/{templateID}": {
        "summary": "Delete a template",
        "description": (
            "Permanently deletes a template and all its builds.\n"
            "\n"
            "**Warning:** This action cannot be undone. Existing sandboxes created\n"
            "from this template will continue to work, but no new sandboxes can be\n"
            "created from it."
        ),
        "operationId": "deleteTemplate",
        "tags": ["Templates"],
        "addResponses": [400, 403, 404],
    },
    "PATCH /templates/{templateID}": {
        "summary": "Update template",
        "description": (
            "Updates template properties (e.g., public/private visibility).\n"
            "\n"
            "**Deprecated:** Use `PATCH /v2/templates/{templateID}` instead."
        ),
        "operationId": "updateTemplate",
        "tags": ["Templates"],
        "responseOverrides": {
            200: {"description": "Template updated"},
        },
        "addResponses": [403, 404, 409],
    },
    "POST /v3/templates": {
        "summary": "Create a new template",
        "description": (
            "Creates a new template and initiates a build. Returns the template ID\n"
            "and build ID to track the build progress."
        ),
        "operationId": "createTemplateV3",
        "tags": ["Templates"],
        "responseOverrides": {
            202: {"description": "Build started"},
        },
        "addResponses": [403, 409, 429],
    },
    "POST /v2/templates": {
        "summary": "Create a new template (v2)",
        "description": (
            "Creates a new template.\n"
            "\n"
            "**Deprecated:** Use `POST /v3/templates` instead."
        ),
        "operationId": "createTemplateV2",
        "tags": ["Templates"],
        "responseOverrides": {
            202: {"description": "Build started"},
        },
        "addResponses": [403, 409, 429],
    },
    "PATCH /v2/templates/{templateID}": {
        "summary": "Update template (v2)",
        "description": "Updates template properties such as visibility (public/private).",
        "operationId": "updateTemplateV2",
        "tags": ["Templates"],
        "responseOverrides": {
            200: {"description": "Template updated"},
        },
        "addResponses": [403, 404, 409],
    },
    "GET /templates/{templateID}/files/{hash}": {
        "summary": "Get build file upload link",
        "description": (
            "Returns a pre-signed upload URL for uploading build layer files\n"
            "as a tar archive."
        ),
        "operationId": "getTemplateFileUploadLink",
        "tags": ["Templates"],
        "responseOverrides": {
            201: {"description": "Upload link"},
        },
        "paramOverrides": {
            "hash": {"description": "SHA256 hash of the tar file"},
        },
        "addResponses": [403, 404, 503],
    },
    "POST /templates/{templateID}/builds/{buildID}": {
        "summary": "Start a template build (legacy)",
        "description": (
            "Starts a previously created template build.\n"
            "\n"
            "**Deprecated:** Use `POST /v2/templates/{templateID}/builds/{buildID}` instead."
        ),
        "operationId": "startTemplateBuildLegacy",
        "tags": ["Templates"],
        "addResponses": [400, 403, 404, 503],
    },
    "POST /v2/templates/{templateID}/builds/{buildID}": {
        "summary": "Start a template build",
        "description": (
            "Triggers the build process for a template. The build must have been\n"
            "previously created and files uploaded."
        ),
        "operationId": "startTemplateBuild",
        "tags": ["Templates"],
        "responseOverrides": {
            202: {"description": "Build started"},
        },
        "addResponses": [400, 403, 404, 503],
    },
    "GET /templates/{templateID}/builds/{buildID}/status": {
        "summary": "Get build status",
        "description": "Returns the current status and logs for a template build.",
        "operationId": "getTemplateBuildStatus",
        "tags": ["Templates"],
        "responseOverrides": {
            200: {"description": "Build status and logs"},
        },
        "addResponses": [400, 403],
    },
    "GET /templates/{templateID}/builds/{buildID}/logs": {
        "summary": "Get build logs",
        "description": "Returns logs from a template build with pagination and filtering options.",
        "operationId": "getTemplateBuildLogs",
        "tags": ["Templates"],
        "addResponses": [400, 403],
    },
    "POST /templates/tags": {
        "summary": "Assign tags to a template build",
        "description": (
            "Assigns one or more tags to a specific template build. Tags can be used\n"
            'to version and identify specific builds (e.g., "latest", "v1.0").'
        ),
        "operationId": "assignTemplateTags",
        "tags": ["Templates"],
        "responseOverrides": {
            201: {"description": "Tags assigned"},
        },
        "addResponses": [403],
    },
    "DELETE /templates/tags": {
        "summary": "Delete tags from templates",
        "description": "Removes tags from template builds.",
        "operationId": "deleteTemplateTags",
        "tags": ["Templates"],
        "responseOverrides": {
            204: {"description": "Tags deleted"},
        },
    },
    "GET /templates/aliases/{alias}": {
        "summary": "Check template by alias",
        "description": "Checks if a template with the given alias exists and returns its ID.",
        "operationId": "getTemplateByAlias",
        "tags": ["Templates"],
        "responseOverrides": {
            200: {"description": "Template found"},
        },
        "paramOverrides": {
            "alias": {"description": "Template alias to look up"},
        },
        "addResponses": [401],
    },
}

# Schema descriptions and examples for polishing raw schemas
SCHEMA_POLISH: dict[str, dict] = {
    "Error": {
        "description": "Error response returned when a request fails",
        "properties": {
            "code": {"description": "HTTP status code", "example": 400},
            "message": {"description": "Human-readable error message", "example": "Invalid request parameters"},
        },
    },
    "NewSandbox": {
        "description": "Request body for creating a new sandbox",
        "properties": {
            "templateID": {
                "description": (
                    "ID of the template to use. Can be a built-in template "
                    "(`base`, `python`, `node`) or a custom template ID."
                ),
                "example": "base",
            },
            "timeout": {
                "description": (
                    "How long the sandbox should stay alive in seconds, measured from "
                    "creation time. The sandbox will automatically terminate after this "
                    "duration unless extended. Maximum: 24 hours (86400 seconds)."
                ),
                "example": 300,
            },
            "autoPause": {
                "description": (
                    "If true, the sandbox will automatically pause instead of "
                    "terminating when the timeout expires."
                ),
                "example": True,
            },
            "metadata": {
                "description": (
                    "Custom key-value metadata to attach to the sandbox. "
                    "Useful for filtering and organizing sandboxes."
                ),
                "example": {"user": "user-123", "project": "code-review", "environment": "staging"},
            },
            "envVars": {
                "description": "Environment variables to set in the sandbox.",
                "example": {"NODE_ENV": "production", "API_URL": "https://api.example.com"},
            },
        },
    },
    "Sandbox": {
        "description": "A sandbox instance that was just created",
        "properties": {
            "sandboxID": {"description": "Unique identifier of the sandbox", "example": "sandbox-abc123xyz"},
            "templateID": {"description": "ID of the template this sandbox was created from", "example": "base"},
            "envdAccessToken": {
                "description": (
                    "Access token for Data Plane API calls. Use this as the "
                    "`X-Access-Token` header when calling sandbox endpoints."
                ),
                "example": "eyJhbGciOiJIUzI1NiIs...",
            },
            "envdVersion": {"description": "Version of the sandbox runtime", "example": "0.1.0"},
            "domain": {"description": "Base domain for accessing the sandbox", "example": "e2b.app"},
        },
    },
    "SandboxDetail": {
        "description": "Detailed information about a sandbox",
        "properties": {
            "sandboxID": {"description": "Unique identifier of the sandbox", "example": "sandbox-abc123xyz"},
            "templateID": {"description": "ID of the template this sandbox was created from", "example": "base"},
            "alias": {"description": "Human-readable alias for the template", "example": "my-python-template"},
            "startedAt": {"description": "When the sandbox was created", "example": "2024-01-15T10:30:00Z"},
            "endAt": {
                "description": "When the sandbox will automatically terminate (can be extended)",
                "example": "2024-01-15T10:45:00Z",
            },
            "cpuCount": {"description": "Number of CPU cores allocated", "example": 2},
            "memoryMB": {"description": "Memory allocated in megabytes", "example": 512},
            "diskSizeMB": {"description": "Disk space allocated in megabytes", "example": 1024},
            "envdAccessToken": {"description": "Access token for Data Plane API calls"},
        },
    },
    "ListedSandbox": {
        "description": "Summary information about a sandbox in a list",
    },
    "Template": {
        "description": "A sandbox template with pre-installed tools and configurations",
        "properties": {
            "templateID": {"description": "Unique identifier of the template", "example": "tpl-abc123"},
            "buildID": {
                "description": "ID of the current (latest successful) build",
                "example": "550e8400-e29b-41d4-a716-446655440000",
            },
            "names": {
                "description": "Human-readable names/aliases for the template",
                "example": ["my-python-env", "team/python-ml"],
            },
            "cpuCount": {"description": "Default CPU cores for sandboxes", "example": 2},
            "memoryMB": {"description": "Default memory in MB", "example": 512},
            "diskSizeMB": {"description": "Default disk size in MB", "example": 1024},
            "spawnCount": {"description": "Total number of sandboxes created from this template", "example": 1542},
        },
    },
    "SandboxMetric": {
        "description": "Resource usage metrics for a sandbox at a point in time",
        "properties": {
            "timestampUnix": {"description": "Unix timestamp (seconds since epoch)", "example": 1705315800},
            "cpuCount": {"description": "Number of CPU cores", "example": 2},
            "cpuUsedPct": {
                "description": "CPU usage as a percentage (0-100 per core, so max is cpuCount * 100)",
                "example": 45.5,
            },
            "memUsed": {"description": "Memory used in bytes", "example": 268435456},
            "memTotal": {"description": "Total memory available in bytes", "example": 536870912},
            "diskUsed": {"description": "Disk space used in bytes", "example": 104857600},
            "diskTotal": {"description": "Total disk space in bytes", "example": 1073741824},
        },
    },
    "Team": {
        "description": "A team in the E2B platform",
    },
}

# Response examples for error responses
RESPONSE_EXAMPLES: dict[int, dict] = {
    400: {"code": 400, "message": "Invalid request: templateID is required"},
    401: {"code": 401, "message": "Invalid API key"},
    403: {"code": 403, "message": "Access denied"},
    404: {"code": 404, "message": "Sandbox not found"},
    409: {"code": 409, "message": "Sandbox is already paused"},
    429: {"code": 429, "message": "You have reached the maximum number of concurrent E2B sandboxes"},
    500: {"code": 500, "message": "Internal server error"},
    503: {"code": 503, "message": "No builder node available"},
    507: {"code": 507, "message": "Not enough disk space available"},
}

RESPONSE_DESCRIPTIONS: dict[int, str] = {
    400: "Bad Request - The request was malformed or missing required parameters",
    401: "Unauthorized - Invalid or missing API key",
    403: "Forbidden - You don't have permission to access this resource",
    404: "Not Found - The requested resource doesn't exist",
    409: "Conflict - The request conflicts with the current state",
    429: "Too Many Requests - Concurrent sandbox or build limit reached",
    500: "Internal Server Error - Something went wrong on our end",
    503: "Service Unavailable - No builder node is currently available",
    507: "Insufficient Storage - Not enough disk space in the sandbox",
}

# Parameter polish
PARAM_POLISH: dict[str, dict] = {
    "templateID": {
        "description": "Unique identifier of the template (e.g., `base`, `python`, or a custom template ID)",
        "example": "base",
    },
    "buildID": {
        "description": "Unique identifier of a template build (UUID format)",
        "example": "550e8400-e29b-41d4-a716-446655440000",
    },
    "sandboxID": {
        "description": "Unique identifier of the sandbox",
        "example": "sandbox-abc123",
    },
    "teamID": {
        "description": "Unique identifier of your team",
    },
    "paginationLimit": {
        "description": "Maximum number of items to return per page (1-100)",
        "example": 50,
    },
    "paginationNextToken": {
        "description": "Cursor for pagination. Use the value from the previous response to get the next page.",
    },
}

# Sandbox server definition
SANDBOX_SERVER = {
    "url": "https://{port}-{sandboxId}.e2b.app",
    "description": "Sandbox Data Plane API",
    "variables": {
        "port": {
            "default": "49982",
            "description": "API port (always 49982)",
        },
        "sandboxId": {
            "default": "your-sandbox-id",
            "description": "Your sandbox ID from the create response",
        },
    },
}

# Simple $ref schemas to inline (these are just type aliases in the infra spec)
INLINE_REFS: dict[str, dict] = {
    "CPUCount": {"type": "integer", "format": "int32", "minimum": 1},
    "MemoryMB": {"type": "integer", "format": "int32", "minimum": 128},
    "DiskSizeMB": {"type": "integer", "format": "int32", "minimum": 0},
    "EnvdVersion": {"type": "string"},
    "SandboxState": {"type": "string", "enum": ["running", "paused"]},
    "SandboxMetadata": {"type": "object", "additionalProperties": {"type": "string"}},
    "EnvVars": {"type": "object", "additionalProperties": {"type": "string"}},
}


# ---------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------------------------

def load_yaml(filepath: str | Path) -> dict:
    """Load and parse a YAML file."""
    filepath = Path(filepath)
    print(f"Loading: {filepath}")
    with open(filepath) as f:
        return yaml.safe_load(f)


# Conventional key ordering for OpenAPI operations
OPERATION_KEY_ORDER = [
    "summary", "description", "operationId", "deprecated", "tags",
    "security", "parameters", "requestBody", "responses",
    "callbacks", "servers",
]


def reorder_operation_keys(spec: dict) -> dict:
    """Reorder OpenAPI operation properties to the conventional order."""
    paths = spec.get("paths")
    if not paths:
        return spec

    for methods in paths.values():
        for key, value in list(methods.items()):
            if key in ("servers", "parameters") or not isinstance(value, dict):
                continue
            # This is an operation object
            ordered = {}
            for k in OPERATION_KEY_ORDER:
                if k in value:
                    ordered[k] = value[k]
            # Add any remaining keys not in the ordered list
            for k in value:
                if k not in ordered:
                    ordered[k] = value[k]
            methods[key] = ordered

    return spec


def save_yaml(filename: str, data: dict, output_dir: Path | None = None) -> Path:
    """Save data as a YAML file with consistent formatting."""
    out_dir = output_dir or Path.cwd()
    output_path = out_dir / filename

    # Custom representer to handle multiline strings nicely
    class CustomDumper(yaml.SafeDumper):
        pass

    def str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    CustomDumper.add_representer(str, str_representer)

    content = yaml.dump(
        data,
        Dumper=CustomDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=1000,
    )

    output_path.write_text(content)
    print(f"Saved: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# REST API PROCESSING
# ---------------------------------------------------------------------------

def process_rest_api(spec: dict) -> dict:
    """Filter and polish REST API endpoints."""
    print("\n=== Processing REST API ===\n")

    filtered_paths = {}

    for path_str, methods in (spec.get("paths") or {}).items():
        # Skip excluded paths
        if path_str in EXCLUDE_REST_PATHS:
            continue

        filtered_methods = {}
        for method, operation in methods.items():
            # Skip non-operation properties
            if not isinstance(operation, dict) or "responses" not in operation:
                continue

            # Only keep endpoints accessible via ApiKeyAuth, unless force-included
            has_api_key_auth = False
            if operation.get("security"):
                for sec_obj in operation["security"]:
                    if "ApiKeyAuth" in sec_obj:
                        has_api_key_auth = True
                        break

            is_force_included = path_str in FORCE_INCLUDE_PATHS
            if not has_api_key_auth and operation.get("security") and not is_force_included:
                continue

            # Clean up security — only keep ApiKeyAuth
            if operation.get("security"):
                operation["security"] = [{"ApiKeyAuth": []}]

            # Apply documentation polish
            polish_key = f"{method.upper()} {path_str}"
            polish = ENDPOINT_POLISH.get(polish_key)
            if polish:
                if polish.get("summary"):
                    operation["summary"] = polish["summary"]
                if polish.get("description"):
                    operation["description"] = polish["description"]
                if polish.get("operationId"):
                    operation["operationId"] = polish["operationId"]
                if polish.get("tags"):
                    operation["tags"] = polish["tags"]

                # Apply response description overrides
                resp_overrides = polish.get("responseOverrides")
                if resp_overrides and operation.get("responses"):
                    for code, overrides in resp_overrides.items():
                        code_str = str(code)
                        if code_str in operation["responses"]:
                            resp = operation["responses"][code_str]
                            if overrides.get("description"):
                                resp["description"] = overrides["description"]
                            if overrides.get("example"):
                                content = resp.get("content", {}).get("application/json")
                                if content:
                                    content["example"] = overrides["example"]

                # Apply parameter overrides
                param_overrides = polish.get("paramOverrides")
                if param_overrides and operation.get("parameters"):
                    for param in operation["parameters"]:
                        override = param_overrides.get(param.get("name"))
                        if override:
                            if override.get("description"):
                                param["description"] = override["description"]
                            if "example" in override:
                                param["example"] = override["example"]

                # Apply request body example
                req_example = polish.get("requestExample")
                if req_example:
                    rb = operation.get("requestBody", {})
                    content = rb.get("content", {}).get("application/json")
                    if content:
                        content["example"] = req_example

                # Add missing error response codes
                add_responses = polish.get("addResponses")
                if add_responses and operation.get("responses") is not None:
                    for code in add_responses:
                        code_str = str(code)
                        if code_str not in operation["responses"]:
                            operation["responses"][code_str] = {
                                "$ref": f"#/components/responses/{code_str}",
                            }

            filtered_methods[method] = operation

        if filtered_methods:
            filtered_paths[path_str] = filtered_methods

    print(f"REST API: {len(filtered_paths)} paths")
    return filtered_paths


# ---------------------------------------------------------------------------
# SANDBOX API PROCESSING
# ---------------------------------------------------------------------------

def process_sandbox_api(spec: dict) -> dict:
    """Filter and polish Sandbox API endpoints."""
    print("\n=== Processing Sandbox API ===\n")

    paths = {}

    for path_str, methods in (spec.get("paths") or {}).items():
        # Skip excluded paths
        if path_str in SANDBOX_EXCLUDE_PATHS:
            continue

        # Add per-path server override
        processed_path: dict = {"servers": [SANDBOX_SERVER]}

        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue

            # Apply sandbox endpoint polish
            polish_key = f"{method.upper()} {path_str}"
            polish = SANDBOX_ENDPOINT_POLISH.get(polish_key)
            if polish:
                if polish.get("summary"):
                    operation["summary"] = polish["summary"]
                if polish.get("description"):
                    operation["description"] = polish["description"]
                if polish.get("operationId"):
                    operation["operationId"] = polish["operationId"]
                if polish.get("tags"):
                    operation["tags"] = polish["tags"]

            # Rename tags
            if operation.get("tags"):
                operation["tags"] = [
                    SANDBOX_TAG_RENAMES.get(tag, tag) for tag in operation["tags"]
                ]

            # Ensure AccessTokenAuth security
            operation["security"] = [{"AccessTokenAuth": []}]

            # Add missing error response codes from sandbox endpoint polish
            if polish and polish.get("addResponses"):
                if operation.get("responses") is None:
                    operation["responses"] = {}
                for code in polish["addResponses"]:
                    code_str = str(code)
                    if code_str not in operation["responses"]:
                        operation["responses"][code_str] = {
                            "$ref": f"#/components/responses/{code_str}",
                        }

            # Add Connect RPC error responses for filesystem/process endpoints
            for prefix, error_codes in CONNECT_RPC_ERRORS.items():
                if path_str.startswith(prefix):
                    if operation.get("responses") is None:
                        operation["responses"] = {}
                    for code in error_codes:
                        code_str = str(code)
                        if code_str not in operation["responses"]:
                            operation["responses"][code_str] = {
                                "$ref": f"#/components/responses/{code_str}",
                            }
                    break

            processed_path[method] = operation

        paths[path_str] = processed_path

    print(f"Sandbox API: {len(paths)} paths")
    return paths


# ---------------------------------------------------------------------------
# COMPONENT PROCESSING
# ---------------------------------------------------------------------------

def build_components(rest_spec: dict, sandbox_spec: dict) -> dict:
    """Build the merged components section."""
    components: dict = {
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            },
            "AccessTokenAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Access-Token",
            },
        },
        "parameters": {},
        "responses": {},
        "schemas": {},
    }

    # Process REST API parameters with polish (excluding admin-only params)
    rest_params = (rest_spec.get("components") or {}).get("parameters") or {}
    for name, param in rest_params.items():
        if name in EXCLUDE_PARAMETERS:
            continue
        polished = dict(param)
        pp = PARAM_POLISH.get(name)
        if pp:
            if pp.get("description"):
                polished["description"] = pp["description"]
            if "example" in pp:
                polished["example"] = pp["example"]
        components["parameters"][name] = polished

    # Add sandbox parameters (with Sandbox prefix to avoid collisions)
    sandbox_params = (sandbox_spec.get("components") or {}).get("parameters") or {}
    for name, param in sandbox_params.items():
        components["parameters"][f"Sandbox{name}"] = param

    # Build polished error responses
    for code, description in RESPONSE_DESCRIPTIONS.items():
        resp: dict = {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Error"},
                },
            },
        }
        if code in RESPONSE_EXAMPLES:
            resp["content"]["application/json"]["example"] = RESPONSE_EXAMPLES[code]
        components["responses"][str(code)] = resp

    # Process REST API schemas
    rest_schemas = (rest_spec.get("components") or {}).get("schemas") or {}
    for name, schema in rest_schemas.items():
        # Skip excluded (admin-only) schemas
        if name in EXCLUDE_SCHEMAS:
            continue
        # Skip simple type alias schemas that we inline
        if name in INLINE_REFS:
            continue

        polished = polish_schema(name, copy.deepcopy(schema))
        components["schemas"][name] = polished

    return components


def polish_schema(name: str, schema: dict) -> dict:
    """Apply documentation polish to a schema definition."""
    polish = SCHEMA_POLISH.get(name)

    # Add top-level description
    if polish and polish.get("description"):
        schema["description"] = polish["description"]

    # Set type to object if not set
    if "type" not in schema and "properties" in schema:
        schema["type"] = "object"

    # Resolve simple $ref properties inline
    if "properties" in schema:
        for prop_name, prop in list(schema["properties"].items()):
            # Resolve $ref to inline types
            if "$ref" in prop:
                ref_name = prop["$ref"].replace("#/components/schemas/", "")
                if ref_name in INLINE_REFS:
                    schema["properties"][prop_name] = dict(INLINE_REFS[ref_name])

            # Resolve allOf with single $ref
            if "allOf" in prop and len(prop["allOf"]) == 1 and "$ref" in prop["allOf"][0]:
                ref_name = prop["allOf"][0]["$ref"].replace("#/components/schemas/", "")
                if ref_name in INLINE_REFS:
                    rest = {k: v for k, v in prop.items() if k != "allOf"}
                    schema["properties"][prop_name] = {**INLINE_REFS[ref_name], **rest}

            # Apply property-level polish
            if polish and polish.get("properties") and prop_name in polish["properties"]:
                prop_polish = polish["properties"][prop_name]
                if prop_polish.get("description"):
                    schema["properties"][prop_name]["description"] = prop_polish["description"]
                if "example" in prop_polish:
                    schema["properties"][prop_name]["example"] = prop_polish["example"]

    return schema


# ---------------------------------------------------------------------------
# POST-PROCESSING
# ---------------------------------------------------------------------------

def resolve_inline_refs(obj):
    """Recursively resolve $ref pointers to INLINE_REFS schemas.

    Also unwraps allOf with a single $ref when pointing to an inline schema.
    """
    if obj is None or not isinstance(obj, (dict, list)):
        return obj

    if isinstance(obj, list):
        return [resolve_inline_refs(item) for item in obj]

    # Handle direct $ref to inline schema
    if "$ref" in obj and isinstance(obj["$ref"], str):
        ref_name = obj["$ref"].replace("#/components/schemas/", "")
        if ref_name in INLINE_REFS:
            return dict(INLINE_REFS[ref_name])

    # Handle allOf with single $ref to inline schema
    if "allOf" in obj and len(obj["allOf"]) == 1 and "$ref" in obj["allOf"][0]:
        ref_name = obj["allOf"][0]["$ref"].replace("#/components/schemas/", "")
        if ref_name in INLINE_REFS:
            rest = {k: v for k, v in obj.items() if k != "allOf"}
            return {**INLINE_REFS[ref_name], **rest}

    # Unwrap allOf with a single $ref (no inline schema, just simplify)
    if "allOf" in obj and len(obj["allOf"]) == 1 and len(obj) == 1:
        return resolve_inline_refs(obj["allOf"][0])

    result = {}
    for key, value in obj.items():
        result[key] = resolve_inline_refs(value)
    return result


def update_sandbox_refs(obj, sandbox_param_names: set):
    """Update $ref references in sandbox paths to use Sandbox prefix."""
    if obj is None or not isinstance(obj, (dict, list)):
        return

    if isinstance(obj, dict):
        if "$ref" in obj and isinstance(obj["$ref"], str):
            import re
            match = re.match(r"^#/components/parameters/(.+)$", obj["$ref"])
            if match and match.group(1) in sandbox_param_names:
                obj["$ref"] = f"#/components/parameters/Sandbox{match.group(1)}"

        for value in obj.values():
            if isinstance(value, (dict, list)):
                update_sandbox_refs(value, sandbox_param_names)

    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                update_sandbox_refs(item, sandbox_param_names)


# ---------------------------------------------------------------------------
# MERGE
# ---------------------------------------------------------------------------

def merge_specs(rest_paths: dict, sandbox_paths: dict, components: dict) -> dict:
    """Merge REST and Sandbox paths into a single spec."""
    print("\n=== Merging Specs ===\n")

    output = {
        "openapi": "3.0.0",
        "info": INFO,
        "servers": [{"url": "https://api.e2b.app", "description": "E2B Control Plane API"}],
        "tags": TAGS,
        "components": components,
        "paths": {},
    }

    # Add sandbox /init first
    init_path = sandbox_paths.get("/init")
    if init_path:
        output["paths"]["/init"] = init_path

    # Add all REST paths
    for path_str, methods in rest_paths.items():
        output["paths"][path_str] = methods

    # Add sandbox paths (data plane) — skip /init which was already added
    for path_str, methods in sandbox_paths.items():
        if path_str == "/init":
            continue
        output["paths"][path_str] = methods

    total_paths = len(output["paths"])
    print(f"Total paths: {total_paths}")

    return output


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def validate_spec(filename: str) -> bool:
    """Validate the spec using mintlify openapi-check if available."""
    try:
        subprocess.run(
            ["mintlify", "openapi-check", filename],
            capture_output=True,
            check=True,
        )
        print(f"  {filename} is valid")
        return True
    except FileNotFoundError:
        print("mintlify CLI not available, skipping validation")
        return True
    except subprocess.CalledProcessError as e:
        output = (e.stdout or b"").decode() + (e.stderr or b"").decode()
        print(f"  {filename} validation failed:\n{output}")
        return False


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate E2B public OpenAPI spec")
    parser.add_argument(
        "--infra-path",
        type=Path,
        default=DEFAULT_INFRA_PATH,
        help="Path to the infra repository clone",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (defaults to current working directory)",
    )
    args = parser.parse_args()

    infra_path = args.infra_path.resolve()
    rest_source = infra_path / "spec" / "openapi.yml"
    sandbox_source = infra_path / "packages" / "envd" / "spec" / "envd.yaml"

    print("OpenAPI Spec Generation Script")
    print("=" * 30)
    print(f"\nInfra path: {infra_path}")

    # Verify source files exist
    if not rest_source.exists():
        print(f"REST API spec not found: {rest_source}")
        print("Clone the infra repo or use --infra-path to specify its location.")
        sys.exit(1)
    if not sandbox_source.exists():
        print(f"Sandbox API spec not found: {sandbox_source}")
        sys.exit(1)

    # Load source specs
    rest_spec = load_yaml(rest_source)
    sandbox_spec = load_yaml(sandbox_source)

    # Process each spec
    rest_paths = process_rest_api(rest_spec)
    sandbox_paths = process_sandbox_api(sandbox_spec)

    # Build components
    components = build_components(rest_spec, sandbox_spec)

    # Track sandbox parameter names for ref updates
    sandbox_param_names = set(
        (sandbox_spec.get("components") or {}).get("parameters", {}).keys()
    )

    # Update $ref references in sandbox paths
    for methods in sandbox_paths.values():
        update_sandbox_refs(methods, sandbox_param_names)

    # Merge into final spec
    merged = merge_specs(rest_paths, sandbox_paths, components)

    # Post-process: resolve inline refs and unwrap unnecessary allOf throughout
    merged = resolve_inline_refs(merged)

    # Reorder operation keys for conventional YAML output
    reorder_operation_keys(merged)

    # Save
    output_path = save_yaml(OUTPUT_FILENAME, merged, output_dir=args.output_dir)

    # Validate
    print("\n=== Validation ===\n")
    validate_spec(str(output_path))

    print("\nDone!\n")


if __name__ == "__main__":
    main()
