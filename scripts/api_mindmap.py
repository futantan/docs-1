#!/usr/bin/env python3
"""
E2B API Reference — Structure Mindmap & Endpoint Grouping

This module defines the target documentation structure for the E2B API reference.
It maps every public endpoint to its documentation group (tag) and provides
a visual tree printer for inspecting the structure.

Run directly to print the mindmap:
    python scripts/api_mindmap.py
"""

# ---------------------------------------------------------------------------
# 1. TARGET STRUCTURE — the goal for the generated docs
# ---------------------------------------------------------------------------

STRUCTURE = {
    "E2B API": {
        "Control Plane (api.e2b.app)": {
            "auth": "X-API-Key header",
            "groups": {
                "Sandboxes": [
                    "POST   /sandboxes                        — Create a sandbox",
                    "GET    /sandboxes                        — List running sandboxes",
                    "GET    /v2/sandboxes                     — List all sandboxes (v2)",
                    "GET    /sandboxes/{sandboxID}            — Get sandbox details",
                    "DELETE /sandboxes/{sandboxID}            — Terminate a sandbox",
                    "POST   /sandboxes/{sandboxID}/pause      — Pause a sandbox",
                    "POST   /sandboxes/{sandboxID}/resume     — Resume (deprecated)",
                    "POST   /sandboxes/{sandboxID}/connect    — Connect to or resume",
                    "POST   /sandboxes/{sandboxID}/timeout    — Set sandbox timeout",
                    "POST   /sandboxes/{sandboxID}/refreshes  — Extend sandbox lifetime",
                    "GET    /sandboxes/{sandboxID}/logs       — Get logs (legacy)",
                    "GET    /v2/sandboxes/{sandboxID}/logs    — Get logs",
                ],
                "Templates": [
                    "GET    /templates                                       — List templates",
                    "POST   /templates                                       — Create template (legacy)",
                    "POST   /v3/templates                                    — Create a new template",
                    "POST   /v2/templates                                    — Create template (v2)",
                    "GET    /templates/{templateID}                           — Get template details",
                    "POST   /templates/{templateID}                           — Rebuild template (legacy)",
                    "DELETE /templates/{templateID}                           — Delete a template",
                    "PATCH  /templates/{templateID}                           — Update template (deprecated)",
                    "PATCH  /v2/templates/{templateID}                        — Update template (v2)",
                    "GET    /templates/{templateID}/files/{hash}              — Get build file upload link",
                    "POST   /templates/{templateID}/builds/{buildID}          — Start build (legacy)",
                    "POST   /v2/templates/{templateID}/builds/{buildID}       — Start a template build",
                    "GET    /templates/{templateID}/builds/{buildID}/status   — Get build status",
                    "GET    /templates/{templateID}/builds/{buildID}/logs     — Get build logs",
                    "POST   /templates/tags                                   — Assign tags",
                    "DELETE /templates/tags                                   — Delete tags",
                    "GET    /templates/aliases/{alias}                        — Check template by alias",
                ],
                "Metrics": [
                    "GET    /sandboxes/metrics                — Batch sandbox metrics",
                    "GET    /sandboxes/{sandboxID}/metrics    — Single sandbox metrics",
                    "GET    /teams/{teamID}/metrics           — Team metrics",
                    "GET    /teams/{teamID}/metrics/max       — Max team metric",
                ],
                # Note: GET /teams excluded (Supabase session auth only)
            },
        },
        "Data Plane ({port}-{sandboxId}.e2b.app)": {
            "auth": "X-Access-Token header",
            "groups": {
                "Sandbox Init (tagged Sandboxes)": [
                    "POST   /init                             — Initialize sandbox",
                ],
                "Sandbox Filesystem": [
                    "GET    /files                            — Download file",
                    "POST   /files                            — Upload file",
                    "POST   /filesystem.Filesystem/ListDir    — List directory contents",
                    "POST   /filesystem.Filesystem/MakeDir    — Create a directory",
                    "POST   /filesystem.Filesystem/Remove     — Delete a file or directory",
                    "POST   /filesystem.Filesystem/Move       — Move or rename",
                    "POST   /filesystem.Filesystem/Stat       — Get file information",
                    "POST   /filesystem.Filesystem/CreateWatcher    — Create watcher",
                    "POST   /filesystem.Filesystem/GetWatcherEvents — Get watcher events",
                    "POST   /filesystem.Filesystem/RemoveWatcher    — Remove watcher",
                    "POST   /filesystem.Filesystem/WatchDir         — Watch directory (streaming)",
                ],
                "Sandbox Process": [
                    "POST   /process.Process/Start            — Start a process",
                    "POST   /process.Process/List             — List running processes",
                    "POST   /process.Process/SendSignal       — Send signal to process",
                    "POST   /process.Process/SendInput        — Send input to process",
                    "POST   /process.Process/Connect          — Connect to process",
                    "POST   /process.Process/StreamInput      — Stream input to process",
                    "POST   /process.Process/Update           — Update a running process",
                ],
            },
        },
    },
}

# ---------------------------------------------------------------------------
# 2. TAGS — the 6 documentation groups with rich descriptions
# ---------------------------------------------------------------------------

TAGS = [
    {
        "name": "Sandboxes",
        "description": (
            "Create and manage sandbox instances. Sandboxes are isolated cloud environments\n"
            "where you can safely run code, install packages, and execute processes.\n"
            "\n"
            "**Common workflows:**\n"
            "- Create a sandbox \u2192 Run code \u2192 Delete sandbox\n"
            "- Create a sandbox \u2192 Pause \u2192 Resume later \u2192 Delete\n"
            "- List running sandboxes \u2192 Get metrics \u2192 Clean up idle ones"
        ),
    },
    {
        "name": "Templates",
        "description": (
            "Build and manage custom templates. Templates are pre-configured sandbox images\n"
            "with your preferred tools, packages, and configurations pre-installed.\n"
            "\n"
            "**Use templates to:**\n"
            "- Speed up sandbox creation by pre-installing dependencies\n"
            "- Ensure consistent environments across sandboxes\n"
            "- Share configurations across your team"
        ),
    },
    {
        "name": "Metrics",
        "description": (
            "Monitor resource usage and track sandbox activity. Use metrics to understand\n"
            "your usage patterns and optimize costs."
        ),
    },
    {
        "name": "Sandbox Filesystem",
        "description": (
            "Perform filesystem operations inside a running sandbox. Create directories,\n"
            "list contents, move files, delete files, and watch for changes.\n"
            "\n"
            "**Base URL:** `https://{port}-{sandboxId}.e2b.app`\n"
            "\n"
            "These endpoints use Connect RPC protocol over HTTP."
        ),
    },
    {
        "name": "Sandbox Process",
        "description": (
            "Start and manage processes inside a running sandbox. Execute commands,\n"
            "stream output, send input, and control running processes.\n"
            "\n"
            "**Base URL:** `https://{port}-{sandboxId}.e2b.app`\n"
            "\n"
            "These endpoints use Connect RPC protocol over HTTP."
        ),
    },
]

# ---------------------------------------------------------------------------
# 3. ENDPOINT → GROUP MAP
# ---------------------------------------------------------------------------

ENDPOINT_GROUPS: dict[tuple[str, str], str] = {
    # === Sandboxes (Control Plane) ===
    ("GET",    "/sandboxes"):                       "Sandboxes",
    ("POST",   "/sandboxes"):                       "Sandboxes",
    ("GET",    "/v2/sandboxes"):                    "Sandboxes",
    ("GET",    "/sandboxes/{sandboxID}"):            "Sandboxes",
    ("DELETE", "/sandboxes/{sandboxID}"):            "Sandboxes",
    ("POST",   "/sandboxes/{sandboxID}/pause"):      "Sandboxes",
    ("POST",   "/sandboxes/{sandboxID}/resume"):     "Sandboxes",
    ("POST",   "/sandboxes/{sandboxID}/connect"):    "Sandboxes",
    ("POST",   "/sandboxes/{sandboxID}/timeout"):    "Sandboxes",
    ("POST",   "/sandboxes/{sandboxID}/refreshes"):  "Sandboxes",
    ("GET",    "/sandboxes/{sandboxID}/logs"):        "Sandboxes",
    ("GET",    "/v2/sandboxes/{sandboxID}/logs"):     "Sandboxes",

    # === Templates (Control Plane) ===
    ("GET",    "/templates"):                                        "Templates",
    ("POST",   "/templates"):                                        "Templates",
    ("GET",    "/templates/{templateID}"):                            "Templates",
    ("POST",   "/templates/{templateID}"):                            "Templates",
    ("DELETE", "/templates/{templateID}"):                            "Templates",
    ("PATCH",  "/templates/{templateID}"):                            "Templates",
    ("POST",   "/v3/templates"):                                     "Templates",
    ("POST",   "/v2/templates"):                                     "Templates",
    ("PATCH",  "/v2/templates/{templateID}"):                        "Templates",
    ("GET",    "/templates/{templateID}/files/{hash}"):              "Templates",
    ("POST",   "/templates/{templateID}/builds/{buildID}"):          "Templates",
    ("POST",   "/v2/templates/{templateID}/builds/{buildID}"):       "Templates",
    ("GET",    "/templates/{templateID}/builds/{buildID}/status"):   "Templates",
    ("GET",    "/templates/{templateID}/builds/{buildID}/logs"):     "Templates",
    ("POST",   "/templates/tags"):                                   "Templates",
    ("DELETE", "/templates/tags"):                                   "Templates",
    ("GET",    "/templates/aliases/{alias}"):                        "Templates",

    # === Metrics (Control Plane) ===
    ("GET",    "/sandboxes/metrics"):               "Metrics",
    ("GET",    "/sandboxes/{sandboxID}/metrics"):   "Metrics",
    ("GET",    "/teams/{teamID}/metrics"):           "Metrics",
    ("GET",    "/teams/{teamID}/metrics/max"):       "Metrics",

    # Note: GET /teams excluded — uses Supabase session auth, not API keys

    # === Sandbox Init (Data Plane, tagged as Sandboxes) ===
    ("POST",   "/init"):                            "Sandboxes",

    # === Sandbox Filesystem (Data Plane) ===
    ("GET",    "/files"):                           "Sandbox Filesystem",
    ("POST",   "/files"):                           "Sandbox Filesystem",
    # /filesystem.Filesystem/* handled by pattern rule in get_group()

    # === Sandbox Process (Data Plane) ===
    # /process.Process/* handled by pattern rule in get_group()
}


def get_group(method: str, path: str) -> str | None:
    """Resolve an endpoint to its documentation group.

    Returns the tag name, or None if the endpoint is not public.
    Uses the explicit ENDPOINT_GROUPS map first, then falls back
    to prefix-based rules for Connect RPC endpoints.
    """
    key = (method.upper(), path)
    if key in ENDPOINT_GROUPS:
        return ENDPOINT_GROUPS[key]
    if path.startswith("/filesystem.Filesystem/"):
        return "Sandbox Filesystem"
    if path.startswith("/process.Process/"):
        return "Sandbox Process"
    return None


# ---------------------------------------------------------------------------
# 4. TREE PRINTER
# ---------------------------------------------------------------------------

def print_tree(node, indent=0, prefix=""):
    """Recursively print a nested dict/list structure as an ASCII tree."""
    spacer = "  " * indent

    if isinstance(node, dict):
        for i, (key, value) in enumerate(node.items()):
            is_last = i == len(node) - 1
            connector = "└── " if is_last else "├── "
            if isinstance(value, str) and key in ("auth",):
                print(f"{spacer}{connector}{key}: {value}")
            elif isinstance(value, (dict, list)):
                print(f"{spacer}{connector}{key}")
                print_tree(value, indent + 1)
            else:
                print(f"{spacer}{connector}{key}: {value}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            is_last = i == len(node) - 1
            connector = "└── " if is_last else "├── "
            print(f"{spacer}{connector}{item}")


def print_group_summary():
    """Print a summary table of groups and their endpoint counts."""
    from collections import Counter
    counts: Counter[str] = Counter()

    # Count explicit entries
    for (_, _), group in ENDPOINT_GROUPS.items():
        counts[group] += 1

    # Count the implicit Connect RPC patterns from the STRUCTURE
    for plane in STRUCTURE["E2B API"].values():
        if not isinstance(plane, dict):
            continue
        for group_name, endpoints in plane.get("groups", {}).items():
            # Normalize the group name (strip parenthetical notes)
            tag = group_name.split(" (")[0] if " (tagged" in group_name else group_name
            for ep in endpoints:
                path = ep.split("—")[0].strip().split(None, 1)[1].strip() if "—" in ep else ep.split(None, 1)[1].strip()
                method = ep.split()[0]
                if (method, path) not in ENDPOINT_GROUPS:
                    counts[tag] += 1

    print("\n  Group Summary")
    print("  " + "=" * 40)
    total = 0
    for tag_def in TAGS:
        name = tag_def["name"]
        c = counts.get(name, 0)
        total += c
        print(f"  {name:<25} {c:>3} endpoints")
    print("  " + "-" * 40)
    print(f"  {'Total':<25} {total:>3} endpoints")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("  E2B API Reference — Documentation Structure Mindmap")
    print("=" * 70)
    print()
    print_tree(STRUCTURE)
    print_group_summary()
    print()
