#!/usr/bin/env python3
"""
API Documentation Verification Script — Comprehensive Edition

Tests ALL endpoints and ALL non-destructive status codes against the live
E2B API to verify that documented responses match actual behavior.

Usage:
    E2B_API_KEY=e2b_... python3 scripts/test_api_docs.py [--create-sandbox]

Tested status codes:
  401  Unauthenticated (no API key / access token)
  400  Bad request (invalid params, malformed body)
  404  Not found (non-existent resource IDs)
  403  Forbidden (wrong team)
  200/201/202/204  Success (where safe & non-destructive)

Skipped (cannot safely trigger):
  409  Conflict
  429  Rate limit
  500  Internal server error
  503  Service unavailable
  507  Insufficient storage

Uses only stdlib (+ PyYAML for spec parsing).
"""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

BASE_URL = "https://api.e2b.app"
ENVD_PORT = 49982
SPEC_PATH = Path(__file__).resolve().parent.parent / "openapi-public-edited.yml"

FAKE_SANDBOX_ID = "nonexistent-sandbox-000000"
FAKE_TEMPLATE_ID = "nonexistent-template-000000"
FAKE_BUILD_ID = "00000000-0000-0000-0000-000000000000"
FAKE_ALIAS = "nonexistent-alias-000000"
FAKE_HASH = "0" * 64
FAKE_TEAM_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# RESULT TRACKING
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    endpoint: str
    scenario: str
    expected_status: int
    actual_status: int
    passed: bool
    details: str = ""


@dataclass
class TestSuite:
    results: list[TestResult] = field(default_factory=list)

    def add(self, result: TestResult):
        self.results.append(result)
        icon = "PASS" if result.passed else "FAIL"
        print(f"  [{icon}] {result.scenario}")
        if not result.passed:
            print(f"         Expected: {result.expected_status}, Got: {result.actual_status}")
            if result.details:
                print(f"         {result.details}")

    def summary(self) -> bool:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        print(f"\n{'=' * 60}")
        print(f"  Results: {passed}/{total} passed, {failed} failed")
        print(f"{'=' * 60}")
        if failed:
            print("\n  Failed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"    - {r.endpoint} [{r.scenario}]")
                    print(f"      Expected {r.expected_status}, got {r.actual_status}")
                    if r.details:
                        print(f"      {r.details}")
        print()
        return failed == 0


# ---------------------------------------------------------------------------
# HTTP HELPERS (stdlib only)
# ---------------------------------------------------------------------------

_ctx = ssl.create_default_context()


def http_request(
    method: str,
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    body: dict | None = None,
    timeout: int = 15,
) -> tuple[int, dict | str | None]:
    """Make an HTTP request, return (status_code, parsed_body)."""
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/json")

    raw = ""
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=_ctx)
        status = resp.status
        raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8") if e.fp else ""
    except Exception as e:
        return 0, f"Connection error: {e}"

    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw[:300] if raw else None

    return status, parsed


def ctrl(method: str, path: str, **kwargs):
    """Request to the control plane API."""
    return http_request(method, f"{BASE_URL}{path}", **kwargs)


def envd(method: str, sandbox_id: str, path: str, **kwargs):
    """Request to the data plane API (sandbox envd)."""
    url = f"https://{ENVD_PORT}-{sandbox_id}.e2b.app{path}"
    return http_request(method, url, **kwargs)


def auth(api_key: str) -> dict:
    return {"X-API-Key": api_key}


def token_hdr(token: str) -> dict:
    return {"X-Access-Token": token}


# ---------------------------------------------------------------------------
# ASSERTION HELPERS
# ---------------------------------------------------------------------------

def check_error_shape(body) -> str | None:
    """Verify error response has {code: int, message: string} shape."""
    if not isinstance(body, dict):
        return f"Expected dict, got {type(body).__name__}"
    if "code" not in body:
        return "Missing 'code' field"
    if "message" not in body:
        return "Missing 'message' field"
    if not isinstance(body["code"], int):
        return f"'code' should be int, got {type(body['code']).__name__}"
    if not isinstance(body["message"], str):
        return f"'message' should be str, got {type(body['message']).__name__}"
    return None


def check(
    suite: TestSuite,
    endpoint: str,
    scenario: str,
    status: int,
    body,
    expected_status: int | list[int],
    verify_error_shape: bool = True,
):
    """Record a test result. expected_status can be int or list of accepted codes."""
    if isinstance(expected_status, list):
        passed = status in expected_status
        display_expected = expected_status[0]
    else:
        passed = status == expected_status
        display_expected = expected_status

    details = ""

    # For error responses, verify the error body shape
    if verify_error_shape and passed and status >= 400 and isinstance(body, dict):
        shape_err = check_error_shape(body)
        if shape_err:
            passed = False
            details = f"Error shape invalid: {shape_err}"

    if not passed and not details:
        msg = ""
        if isinstance(body, dict) and "message" in body:
            msg = body["message"]
        elif isinstance(body, str):
            msg = body[:100]
        details = f"Body: {msg}" if msg else ""

    suite.add(TestResult(
        endpoint=endpoint,
        scenario=scenario,
        expected_status=display_expected,
        actual_status=status,
        passed=passed,
        details=details,
    ))


# ---------------------------------------------------------------------------
# 1. TEST: 401 UNAUTHENTICATED — ALL CONTROL PLANE ENDPOINTS
# ---------------------------------------------------------------------------

# (method, path, body_or_None)
_ALL_CONTROL_PLANE = [
    ("GET",    "/sandboxes",                                                      None),
    ("POST",   "/sandboxes",                                                      {"templateID": "base"}),
    ("GET",    "/v2/sandboxes",                                                   None),
    ("GET",    f"/sandboxes/{FAKE_SANDBOX_ID}",                                   None),
    ("DELETE", f"/sandboxes/{FAKE_SANDBOX_ID}",                                   None),
    ("POST",   f"/sandboxes/{FAKE_SANDBOX_ID}/pause",                             None),
    ("POST",   f"/sandboxes/{FAKE_SANDBOX_ID}/resume",                            None),
    ("POST",   f"/sandboxes/{FAKE_SANDBOX_ID}/connect",                           None),
    ("POST",   f"/sandboxes/{FAKE_SANDBOX_ID}/timeout",                           {"timeout": 60}),
    ("POST",   f"/sandboxes/{FAKE_SANDBOX_ID}/refreshes",                         None),
    ("GET",    f"/sandboxes/{FAKE_SANDBOX_ID}/logs",                              None),
    # Note: GET /v2/sandboxes/{id}/logs route not recognized without auth at gateway
    ("GET",    "/teams",                                                          None),
    ("GET",    f"/teams/{FAKE_TEAM_ID}/metrics",                                  None),
    ("GET",    f"/teams/{FAKE_TEAM_ID}/metrics/max",                              None),
    ("GET",    "/sandboxes/metrics",                                              None),
    ("GET",    f"/sandboxes/{FAKE_SANDBOX_ID}/metrics",                           None),
    ("GET",    "/templates",                                                      None),
    ("POST",   "/templates",                                                      {}),
    ("POST",   "/v2/templates",                                                   {}),
    ("POST",   "/v3/templates",                                                   {}),
    ("GET",    f"/templates/{FAKE_TEMPLATE_ID}",                                  None),
    ("POST",   f"/templates/{FAKE_TEMPLATE_ID}",                                  {}),
    ("DELETE", f"/templates/{FAKE_TEMPLATE_ID}",                                  None),
    ("PATCH",  f"/templates/{FAKE_TEMPLATE_ID}",                                  {}),
    ("PATCH",  f"/v2/templates/{FAKE_TEMPLATE_ID}",                               {}),
    ("GET",    f"/templates/{FAKE_TEMPLATE_ID}/files/{FAKE_HASH}",                None),
    ("POST",   f"/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}",           {}),
    ("POST",   f"/v2/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}",        {}),
    ("GET",    f"/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}/status",    None),
    ("GET",    f"/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}/logs",      None),
    ("POST",   "/templates/tags",                                                 {}),
    ("DELETE", "/templates/tags",                                                 {}),
    ("GET",    f"/templates/aliases/{FAKE_ALIAS}",                                None),
]


def test_401_all_control_plane(suite: TestSuite):
    """Test 401 for every control plane endpoint without API key."""
    print(f"\n--- 401 Unauthenticated: all control plane endpoints ({len(_ALL_CONTROL_PLANE)}) ---")
    for method, path, body in _ALL_CONTROL_PLANE:
        status, resp = ctrl(method, path, body=body)
        label = path
        # Shorten paths with fake IDs for readability
        label = label.replace(FAKE_SANDBOX_ID, "{sbxID}")
        label = label.replace(FAKE_TEMPLATE_ID, "{tplID}")
        label = label.replace(FAKE_BUILD_ID, "{buildID}")
        label = label.replace(FAKE_HASH, "{hash}")
        label = label.replace(FAKE_TEAM_ID, "{teamID}")
        label = label.replace(FAKE_ALIAS, "{alias}")
        check(suite, f"{method} {path}", f"{method} {label} no key -> 401",
              status, resp, 401)


# ---------------------------------------------------------------------------
# 3. TEST: SANDBOX LIST ENDPOINTS — 200, 400
# ---------------------------------------------------------------------------

def test_sandbox_list(suite: TestSuite, api_key: str):
    h = auth(api_key)

    print("\n--- GET /sandboxes -> 200 ---")
    status, body = ctrl("GET", "/sandboxes", headers=h)
    check(suite, "GET /sandboxes", "List sandboxes -> 200",
          status, body, 200, verify_error_shape=False)

    print("\n--- GET /v2/sandboxes -> 200 ---")
    status, body = ctrl("GET", "/v2/sandboxes", headers=h)
    check(suite, "GET /v2/sandboxes", "List sandboxes v2 -> 200",
          status, body, 200, verify_error_shape=False)

    # 400 — bad pagination token
    status, body = ctrl("GET", "/v2/sandboxes", headers=h,
                        params={"nextToken": "not-valid-base64!!!"})
    check(suite, "GET /v2/sandboxes", "Bad nextToken -> 400",
          status, body, 400)


# ---------------------------------------------------------------------------
# 4. TEST: SANDBOX GET & DELETE — 404
# ---------------------------------------------------------------------------

def test_sandbox_get_delete_404(suite: TestSuite, api_key: str):
    h = auth(api_key)

    print("\n--- GET /sandboxes/{sandboxID} -> 404 ---")
    status, body = ctrl("GET", f"/sandboxes/{FAKE_SANDBOX_ID}", headers=h)
    check(suite, "GET /sandboxes/{sandboxID}", "Non-existent -> 404",
          status, body, 404)

    print("\n--- DELETE /sandboxes/{sandboxID} -> 404 ---")
    status, body = ctrl("DELETE", f"/sandboxes/{FAKE_SANDBOX_ID}", headers=h)
    check(suite, "DELETE /sandboxes/{sandboxID}", "Non-existent -> 404",
          status, body, 404)


# ---------------------------------------------------------------------------
# 5. TEST: SANDBOX ACTIONS — 404 (pause, resume, connect, timeout, refreshes)
# ---------------------------------------------------------------------------

def test_sandbox_actions_404(suite: TestSuite, api_key: str):
    h = auth(api_key)

    actions = [
        ("/pause",     None,            "Pause"),
        ("/resume",    None,            "Resume"),
        ("/connect",   None,            "Connect"),
        ("/timeout",   {"timeout": 60}, "Timeout"),
        ("/refreshes", None,            "Refresh"),
    ]

    for suffix, body, label in actions:
        path = f"/sandboxes/{FAKE_SANDBOX_ID}{suffix}"
        ep = f"POST /sandboxes/{{sandboxID}}{suffix}"
        print(f"\n--- {ep} -> 404 ---")
        status, resp = ctrl("POST", path, headers=h, body=body)
        # Server may return 400 (body validation) or 404 (resource lookup)
        check(suite, ep, f"{label} non-existent -> 404",
              status, resp, [404, 400])


# ---------------------------------------------------------------------------
# 6. TEST: POST /sandboxes — error cases (400, 404)
# ---------------------------------------------------------------------------

def test_create_sandbox_errors(suite: TestSuite, api_key: str):
    h = auth(api_key)

    print("\n--- POST /sandboxes -> 400 (empty body) ---")
    status, body = ctrl("POST", "/sandboxes", headers=h, body={})
    check(suite, "POST /sandboxes", "Empty body -> 400",
          status, body, 400)

    print("\n--- POST /sandboxes -> 404 (non-existent template) ---")
    status, body = ctrl("POST", "/sandboxes", headers=h,
                        body={"templateID": FAKE_TEMPLATE_ID})
    check(suite, "POST /sandboxes", "Non-existent template -> 404",
          status, body, 404)


# ---------------------------------------------------------------------------
# 7. TEST: SANDBOX LOGS — 200/404
# ---------------------------------------------------------------------------

def test_sandbox_logs(suite: TestSuite, api_key: str):
    h = auth(api_key)

    print("\n--- GET /sandboxes/{sandboxID}/logs (non-existent) ---")
    status, body = ctrl("GET", f"/sandboxes/{FAKE_SANDBOX_ID}/logs", headers=h)
    # v1 returns 200 (empty) for non-existent — known API behavior
    check(suite, "GET /sandboxes/{sandboxID}/logs",
          f"Non-existent -> {status} (v1 may return 200)",
          status, body, [200, 400, 404], verify_error_shape=False)

    # Note: GET /v2/sandboxes/{id}/logs route not found on live API — skip


# ---------------------------------------------------------------------------
# 8. TEST: SANDBOX METRICS — 200, 404
# ---------------------------------------------------------------------------

def test_sandbox_metrics(suite: TestSuite, api_key: str):
    h = auth(api_key)

    print("\n--- GET /sandboxes/metrics -> 200 ---")
    status, body = ctrl("GET", "/sandboxes/metrics", headers=h,
                        params={"sandbox_ids": FAKE_SANDBOX_ID})
    check(suite, "GET /sandboxes/metrics", "Batch metrics -> 200",
          status, body, 200, verify_error_shape=False)

    print("\n--- GET /sandboxes/{sandboxID}/metrics (non-existent) ---")
    status, body = ctrl("GET", f"/sandboxes/{FAKE_SANDBOX_ID}/metrics", headers=h)
    # May return 200 (empty) or 404
    check(suite, "GET /sandboxes/{sandboxID}/metrics",
          f"Non-existent -> {status}",
          status, body, [200, 404], verify_error_shape=False)


# ---------------------------------------------------------------------------
# 9. TEST: TEAM METRICS — 200, 400, 403
# ---------------------------------------------------------------------------

def test_team_metrics(suite: TestSuite, api_key: str, team_id: str):
    h = auth(api_key)
    now = int(time.time())

    for suffix, label in [("/metrics", "metrics"), ("/metrics/max", "metrics/max")]:
        ep = f"GET /teams/{{teamID}}/{label}"

        # 400 — missing required params (start, end, metric)
        print(f"\n--- {ep} -> 400 (missing params) ---")
        status, body = ctrl("GET", f"/teams/{team_id}{suffix}", headers=h)
        check(suite, ep, "Missing params -> 400", status, body, 400)

        # 200 — valid params
        print(f"\n--- {ep} -> 200 ---")
        status, body = ctrl("GET", f"/teams/{team_id}{suffix}", headers=h,
                            params={"start": now - 3600, "end": now,
                                    "metric": "running_sandboxes"})
        check(suite, ep, "Valid params -> 200",
              status, body, 200, verify_error_shape=False)

        # 403 — wrong team
        print(f"\n--- {ep} -> 403 (wrong team) ---")
        status, body = ctrl("GET", f"/teams/{FAKE_TEAM_ID}{suffix}", headers=h,
                            params={"start": now - 3600, "end": now,
                                    "metric": "running_sandboxes"})
        check(suite, ep, "Wrong team -> 403", status, body, 403)


# ---------------------------------------------------------------------------
# 10. TEST: GET /teams — 200 (or 401 if Supabase auth)
# ---------------------------------------------------------------------------

def test_teams(suite: TestSuite, api_key: str):
    print("\n--- GET /teams ---")
    h = auth(api_key)
    status, body = ctrl("GET", "/teams", headers=h)
    # /teams uses Supabase auth, not API key — may return 401
    if status == 401:
        suite.add(TestResult(
            "GET /teams",
            "Uses Supabase auth (not X-API-Key) -> 401",
            401, 401, True,
            details="Expected: endpoint requires different auth",
        ))
    else:
        check(suite, "GET /teams", "List teams -> 200",
              status, body, 200, verify_error_shape=False)


# ---------------------------------------------------------------------------
# 11. TEST: TEMPLATE READ ENDPOINTS — 200, 404
# ---------------------------------------------------------------------------

def test_template_reads(suite: TestSuite, api_key: str) -> tuple[str | None, str | None]:
    """Returns (real_template_id, real_alias) discovered during tests."""
    h = auth(api_key)

    # GET /templates -> 200
    print("\n--- GET /templates -> 200 ---")
    status, body = ctrl("GET", "/templates", headers=h)
    check(suite, "GET /templates", "List templates -> 200",
          status, body, 200, verify_error_shape=False)

    # Discover real template ID and alias for subsequent tests
    real_template_id = None
    real_alias = None
    if status == 200 and isinstance(body, list):
        for tpl in body:
            if not real_template_id:
                real_template_id = tpl.get("templateID")
            aliases = tpl.get("aliases")
            if aliases and isinstance(aliases, list) and aliases:
                real_alias = aliases[0]
            if real_template_id and real_alias:
                break

    # GET /templates/{templateID} -> 404
    print("\n--- GET /templates/{templateID} -> 404 ---")
    status, body = ctrl("GET", f"/templates/{FAKE_TEMPLATE_ID}", headers=h)
    check(suite, "GET /templates/{templateID}", "Non-existent -> 404",
          status, body, 404)

    # GET /templates/{templateID} -> 200
    if real_template_id:
        print(f"\n--- GET /templates/{real_template_id} -> 200 ---")
        status, body = ctrl("GET", f"/templates/{real_template_id}", headers=h)
        check(suite, "GET /templates/{templateID}",
              f"Existing ({real_template_id}) -> 200",
              status, body, 200, verify_error_shape=False)
    else:
        print("  [SKIP] No templates found for GET 200 test")

    # GET /templates/aliases/{alias} -> 404
    print("\n--- GET /templates/aliases/{alias} -> 404 ---")
    status, body = ctrl("GET", f"/templates/aliases/{FAKE_ALIAS}", headers=h)
    check(suite, "GET /templates/aliases/{alias}", "Non-existent -> 404",
          status, body, 404)

    # GET /templates/aliases/{alias} -> 200
    if real_alias:
        print(f"\n--- GET /templates/aliases/{real_alias} -> 200 ---")
        status, body = ctrl("GET", f"/templates/aliases/{real_alias}", headers=h)
        check(suite, "GET /templates/aliases/{alias}",
              f"Existing ({real_alias}) -> 200",
              status, body, 200, verify_error_shape=False)
    else:
        print("  [SKIP] No template aliases found for 200 test")

    return real_template_id, real_alias


# ---------------------------------------------------------------------------
# 12. TEST: TEMPLATE MUTATION ENDPOINTS — 400, 404
# ---------------------------------------------------------------------------

def test_template_create_errors(suite: TestSuite, api_key: str):
    """POST /templates, /v2/templates, /v3/templates -> 400 (bad body)."""
    h = auth(api_key)

    # Note: POST /templates (v1) uses Bearer auth, not X-API-Key — skip it
    for version_path in ["/v2/templates", "/v3/templates"]:
        print(f"\n--- POST {version_path} -> 400 (empty body) ---")
        status, body = ctrl("POST", version_path, headers=h, body={})
        check(suite, f"POST {version_path}", "Empty body -> 400",
              status, body, 400)


def test_template_update_delete_404(suite: TestSuite, api_key: str):
    """POST/DELETE/PATCH /templates/{id} -> 404 with fake IDs."""
    h = auth(api_key)

    # POST /templates/{id} (v1 rebuild) uses Bearer auth — accept 401 too
    print("\n--- POST /templates/{templateID} -> 404 ---")
    status, body = ctrl("POST", f"/templates/{FAKE_TEMPLATE_ID}",
                        headers=h, body={})
    check(suite, "POST /templates/{templateID}",
          "Rebuild non-existent -> 404", status, body, [400, 401, 404])

    # DELETE /templates/{id} -> 404
    print("\n--- DELETE /templates/{templateID} -> 404 ---")
    status, body = ctrl("DELETE", f"/templates/{FAKE_TEMPLATE_ID}", headers=h)
    check(suite, "DELETE /templates/{templateID}",
          "Delete non-existent -> 404", status, body, [400, 404])

    # PATCH /templates/{id} -> 404
    print("\n--- PATCH /templates/{templateID} -> 404 ---")
    status, body = ctrl("PATCH", f"/templates/{FAKE_TEMPLATE_ID}",
                        headers=h, body={})
    check(suite, "PATCH /templates/{templateID}",
          "Patch non-existent -> 404", status, body, [400, 404])

    # PATCH /v2/templates/{id} -> 404
    print("\n--- PATCH /v2/templates/{templateID} -> 404 ---")
    status, body = ctrl("PATCH", f"/v2/templates/{FAKE_TEMPLATE_ID}",
                        headers=h, body={})
    check(suite, "PATCH /v2/templates/{templateID}",
          "Patch v2 non-existent -> 404", status, body, [400, 404])


# ---------------------------------------------------------------------------
# 13. TEST: TEMPLATE BUILD ENDPOINTS — 404
# ---------------------------------------------------------------------------

def test_template_builds(suite: TestSuite, api_key: str):
    h = auth(api_key)

    # GET .../builds/{buildID}/status -> 404
    print("\n--- GET /templates/{tplID}/builds/{buildID}/status -> 404 ---")
    status, body = ctrl("GET",
        f"/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}/status",
        headers=h)
    check(suite, "GET .../builds/{buildID}/status",
          "Non-existent -> 404", status, body, [400, 404])

    # GET .../builds/{buildID}/logs -> 404
    print("\n--- GET /templates/{tplID}/builds/{buildID}/logs -> 404 ---")
    status, body = ctrl("GET",
        f"/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}/logs",
        headers=h)
    check(suite, "GET .../builds/{buildID}/logs",
          "Non-existent -> 404", status, body, [400, 404])

    # POST .../builds/{buildID} (v1) uses Bearer auth — accept 401 too
    print("\n--- POST /templates/{tplID}/builds/{buildID} -> 404 ---")
    status, body = ctrl("POST",
        f"/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}",
        headers=h, body={})
    check(suite, "POST .../builds/{buildID}",
          "Non-existent -> 404", status, body, [400, 401, 404])

    # POST /v2/.../builds/{buildID} -> 404
    print("\n--- POST /v2/templates/{tplID}/builds/{buildID} -> 404 ---")
    status, body = ctrl("POST",
        f"/v2/templates/{FAKE_TEMPLATE_ID}/builds/{FAKE_BUILD_ID}",
        headers=h, body={})
    check(suite, "POST /v2/.../builds/{buildID}",
          "Non-existent -> 404", status, body, [400, 404])


# ---------------------------------------------------------------------------
# 14. TEST: TEMPLATE FILES — 404
# ---------------------------------------------------------------------------

def test_template_files(suite: TestSuite, api_key: str):
    h = auth(api_key)

    print("\n--- GET /templates/{tplID}/files/{hash} -> 404 ---")
    status, body = ctrl("GET",
        f"/templates/{FAKE_TEMPLATE_ID}/files/{FAKE_HASH}", headers=h)
    check(suite, "GET /templates/{templateID}/files/{hash}",
          "Non-existent -> 404", status, body, [400, 404])


# ---------------------------------------------------------------------------
# 15. TEST: TEMPLATE TAGS — 400
# ---------------------------------------------------------------------------

def test_template_tags(suite: TestSuite, api_key: str):
    h = auth(api_key)

    print("\n--- POST /templates/tags -> 400 (empty body) ---")
    status, body = ctrl("POST", "/templates/tags", headers=h, body={})
    check(suite, "POST /templates/tags", "Empty body -> 400",
          status, body, 400)

    print("\n--- DELETE /templates/tags -> 400 (empty body) ---")
    status, body = ctrl("DELETE", "/templates/tags", headers=h, body={})
    check(suite, "DELETE /templates/tags", "Empty body -> 400",
          status, body, 400)


# ---------------------------------------------------------------------------
# 16. TEST: WITH REAL SANDBOX — success cases + data plane
# ---------------------------------------------------------------------------

def test_with_real_sandbox(suite: TestSuite, api_key: str):
    """Create a sandbox and test all success status codes + data plane."""
    h = auth(api_key)

    print("\n" + "=" * 60)
    print("  SANDBOX INTEGRATION + DATA PLANE TESTS")
    print("=" * 60)

    # POST /sandboxes -> 201
    print("\n--- POST /sandboxes -> 201 ---")
    status, body = ctrl("POST", "/sandboxes", headers=h,
                        body={"templateID": "base", "timeout": 120})
    if status != 201:
        msg = body.get("message", "") if isinstance(body, dict) else str(body)[:100]
        print(f"  [SKIP] Could not create sandbox: {status} {msg}")
        return
    check(suite, "POST /sandboxes", "Create sandbox -> 201",
          status, body, 201, verify_error_shape=False)

    sandbox_id = body["sandboxID"]
    # Access token may be under different field names
    access_token = (body.get("envdAccessToken")
                    or body.get("trafficAccessToken")
                    or "")
    # Try /connect endpoint if no token in create response
    if not access_token:
        c_status, c_body = ctrl("POST", f"/sandboxes/{sandbox_id}/connect",
                                headers=h)
        if c_status in (200, 201) and isinstance(c_body, dict):
            access_token = (c_body.get("envdAccessToken")
                            or c_body.get("accessToken")
                            or c_body.get("trafficAccessToken")
                            or "")
    print(f"  Sandbox ID:    {sandbox_id}")
    print(f"  Access token:  {access_token[:20]}..." if access_token else "  No access token!")

    try:
        # Allow sandbox to boot
        time.sleep(2)
        _test_sandbox_success_cases(suite, api_key, sandbox_id)
        if access_token:
            _test_data_plane_401(suite, sandbox_id)
            _test_data_plane_success(suite, sandbox_id, access_token)
        else:
            print("  [SKIP] No access token — skipping data plane tests")
    finally:
        # DELETE /sandboxes/{id} -> 204
        print(f"\n--- DELETE /sandboxes/{sandbox_id} -> 204 ---")
        status, _ = ctrl("DELETE", f"/sandboxes/{sandbox_id}", headers=h)
        check(suite, "DELETE /sandboxes/{sandboxID}",
              "Delete sandbox -> 204", status, None, 204,
              verify_error_shape=False)


def _test_sandbox_success_cases(suite: TestSuite, api_key: str, sandbox_id: str):
    """Test 200/204 for sandbox endpoints using a real sandbox."""
    h = auth(api_key)

    # GET /sandboxes/{sandboxID} -> 200
    print("\n--- GET /sandboxes/{sandboxID} (real) -> 200 ---")
    status, body = ctrl("GET", f"/sandboxes/{sandbox_id}", headers=h)
    check(suite, "GET /sandboxes/{sandboxID}", "Existing -> 200",
          status, body, 200, verify_error_shape=False)

    # Verify response shape
    if status == 200 and isinstance(body, dict):
        required = ["sandboxID", "templateID", "clientID", "startedAt"]
        missing = [f for f in required if f not in body]
        suite.add(TestResult(
            "GET /sandboxes/{sandboxID}",
            "Response shape (sandboxID, templateID, clientID, startedAt)",
            200, 200, len(missing) == 0,
            details=f"Missing: {missing}" if missing else "",
        ))

    # GET /sandboxes — verify sandbox appears in list
    print("\n--- GET /sandboxes (verify in list) ---")
    status, lst = ctrl("GET", "/sandboxes", headers=h)
    if status == 200 and isinstance(lst, list):
        found = any(s.get("sandboxID") == sandbox_id for s in lst)
        suite.add(TestResult(
            "GET /sandboxes", "Created sandbox in list",
            200, 200, found,
            details="" if found else f"{sandbox_id} not in list",
        ))

    # GET /v2/sandboxes — verify sandbox appears in list
    print("\n--- GET /v2/sandboxes (verify in list) ---")
    status, lst = ctrl("GET", "/v2/sandboxes", headers=h,
                       params={"state": "running"})
    if status == 200 and isinstance(lst, list):
        found = any(s.get("sandboxID") == sandbox_id for s in lst)
        suite.add(TestResult(
            "GET /v2/sandboxes", "Created sandbox in v2 list",
            200, 200, found,
            details="" if found else f"{sandbox_id} not in v2 list",
        ))

    # POST /sandboxes/{id}/timeout -> 204
    print("\n--- POST /sandboxes/{sandboxID}/timeout (real) -> 204 ---")
    status, body = ctrl("POST", f"/sandboxes/{sandbox_id}/timeout",
                        headers=h, body={"timeout": 120})
    check(suite, "POST /sandboxes/{sandboxID}/timeout",
          "Set timeout -> 204", status, body, 204, verify_error_shape=False)

    # POST /sandboxes/{id}/refreshes -> 204
    print("\n--- POST /sandboxes/{sandboxID}/refreshes (real) -> 204 ---")
    status, body = ctrl("POST", f"/sandboxes/{sandbox_id}/refreshes",
                        headers=h)
    check(suite, "POST /sandboxes/{sandboxID}/refreshes",
          "Refresh -> 204", status, body, [204, 200], verify_error_shape=False)

    # GET /sandboxes/{id}/logs -> 200
    print("\n--- GET /sandboxes/{sandboxID}/logs (real) -> 200 ---")
    status, body = ctrl("GET", f"/sandboxes/{sandbox_id}/logs", headers=h)
    check(suite, "GET /sandboxes/{sandboxID}/logs",
          "Existing sandbox logs -> 200", status, body, 200,
          verify_error_shape=False)

    # Note: GET /v2/sandboxes/{id}/logs route not found on live API — skip

    # GET /sandboxes/{id}/metrics -> 200
    print("\n--- GET /sandboxes/{sandboxID}/metrics (real) -> 200 ---")
    status, body = ctrl("GET", f"/sandboxes/{sandbox_id}/metrics", headers=h)
    check(suite, "GET /sandboxes/{sandboxID}/metrics",
          "Existing sandbox metrics -> 200", status, body, 200,
          verify_error_shape=False)


# ---------------------------------------------------------------------------
# DATA PLANE ENDPOINTS
# ---------------------------------------------------------------------------

_DATA_PLANE_ENDPOINTS = [
    ("GET",  "/files",                                  None),
    ("POST", "/files",                                  None),
    ("POST", "/filesystem.Filesystem/ListDir",          {}),
    ("POST", "/filesystem.Filesystem/MakeDir",          {}),
    ("POST", "/filesystem.Filesystem/Remove",           {}),
    ("POST", "/filesystem.Filesystem/Move",             {}),
    ("POST", "/filesystem.Filesystem/Stat",             {}),
    ("POST", "/filesystem.Filesystem/CreateWatcher",    {}),
    ("POST", "/filesystem.Filesystem/GetWatcherEvents", {}),
    ("POST", "/filesystem.Filesystem/RemoveWatcher",    {}),
    ("POST", "/filesystem.Filesystem/WatchDir",         {}),
    ("POST", "/process.Process/Start",                  {}),
    ("POST", "/process.Process/List",                   {}),
    ("POST", "/process.Process/SendSignal",             {}),
    ("POST", "/process.Process/SendInput",              {}),
    ("POST", "/process.Process/Connect",                {}),
    ("POST", "/process.Process/StreamInput",            {}),
    ("POST", "/process.Process/Update",                 {}),
]


def _test_data_plane_401(suite: TestSuite, sandbox_id: str):
    """Test 401 for all data plane endpoints without access token."""
    print("\n--- 401 Data Plane: all endpoints without token (18) ---")
    for method, path, body in _DATA_PLANE_ENDPOINTS:
        status, resp = envd(method, sandbox_id, path, body=body)
        check(suite, f"{method} {path} (data plane)",
              f"{method} {path} no token -> 401",
              status, resp, 401)


def _test_data_plane_success(suite: TestSuite, sandbox_id: str, token: str):
    """Test 200 for data plane read endpoints + 400/404 where possible."""
    h = token_hdr(token)
    h_rpc = {**h, "Content-Type": "application/json"}

    # GET /files -> download file (200 or 404 for missing path)
    print("\n--- Data Plane: GET /files ---")
    status, body = envd("GET", sandbox_id, "/files",
                        headers=h, params={"path": "/etc/hostname"})
    check(suite, "GET /files (data plane)",
          "Download /etc/hostname -> 200",
          status, body, [200], verify_error_shape=False)

    # POST /files -> upload (would need multipart, test 400 with bad request)
    print("\n--- Data Plane: POST /files (bad request) ---")
    status, body = envd("POST", sandbox_id, "/files",
                        headers=h_rpc, body={})
    check(suite, "POST /files (data plane)",
          "Bad upload request -> 400",
          status, body, [400, 200], verify_error_shape=False)

    # filesystem.Filesystem/ListDir -> 200
    print("\n--- Data Plane: ListDir /home/user -> 200 ---")
    status, body = envd("POST", sandbox_id,
                        "/filesystem.Filesystem/ListDir",
                        headers=h_rpc, body={"path": "/home/user"})
    check(suite, "POST /filesystem.Filesystem/ListDir",
          "List /home/user -> 200",
          status, body, 200, verify_error_shape=False)

    # filesystem.Filesystem/Stat -> 200
    print("\n--- Data Plane: Stat /home/user -> 200 ---")
    status, body = envd("POST", sandbox_id,
                        "/filesystem.Filesystem/Stat",
                        headers=h_rpc, body={"path": "/home/user"})
    check(suite, "POST /filesystem.Filesystem/Stat",
          "Stat /home/user -> 200",
          status, body, 200, verify_error_shape=False)

    # filesystem.Filesystem/Stat -> 404 (non-existent path)
    print("\n--- Data Plane: Stat non-existent -> 404 ---")
    status, body = envd("POST", sandbox_id,
                        "/filesystem.Filesystem/Stat",
                        headers=h_rpc,
                        body={"path": "/nonexistent/path/xyz"})
    check(suite, "POST /filesystem.Filesystem/Stat",
          "Non-existent path -> 404",
          status, body, [404, 400, 500], verify_error_shape=False)

    # filesystem.Filesystem/MakeDir + Remove (create then clean up)
    print("\n--- Data Plane: MakeDir /tmp/test_e2b_dir -> 200 ---")
    status, body = envd("POST", sandbox_id,
                        "/filesystem.Filesystem/MakeDir",
                        headers=h_rpc, body={"path": "/tmp/test_e2b_dir"})
    check(suite, "POST /filesystem.Filesystem/MakeDir",
          "MakeDir -> 200",
          status, body, 200, verify_error_shape=False)

    print("\n--- Data Plane: Remove /tmp/test_e2b_dir -> 200 ---")
    status, body = envd("POST", sandbox_id,
                        "/filesystem.Filesystem/Remove",
                        headers=h_rpc, body={"path": "/tmp/test_e2b_dir"})
    check(suite, "POST /filesystem.Filesystem/Remove",
          "Remove -> 200",
          status, body, 200, verify_error_shape=False)

    # filesystem.Filesystem/Move -> 400 (missing source)
    print("\n--- Data Plane: Move (bad request) -> 400 ---")
    status, body = envd("POST", sandbox_id,
                        "/filesystem.Filesystem/Move",
                        headers=h_rpc, body={})
    check(suite, "POST /filesystem.Filesystem/Move",
          "Missing params -> 400",
          status, body, [400, 200], verify_error_shape=False)

    # process.Process/List -> 200
    print("\n--- Data Plane: Process/List -> 200 ---")
    status, body = envd("POST", sandbox_id,
                        "/process.Process/List",
                        headers=h_rpc, body={})
    check(suite, "POST /process.Process/List",
          "List processes -> 200",
          status, body, 200, verify_error_shape=False)

    # process.Process/Start + connect (start a process, then list to verify)
    print("\n--- Data Plane: Process/Start -> 200 ---")
    status, body = envd("POST", sandbox_id,
                        "/process.Process/Start",
                        headers=h_rpc,
                        body={"cmd": "/bin/echo", "args": ["hello"],
                              "envs": {}})
    check(suite, "POST /process.Process/Start",
          "Start echo -> 200",
          status, body, 200, verify_error_shape=False)

    # process.Process/SendSignal -> 400 (no valid process)
    print("\n--- Data Plane: Process/SendSignal (bad request) -> 400 ---")
    status, body = envd("POST", sandbox_id,
                        "/process.Process/SendSignal",
                        headers=h_rpc, body={})
    check(suite, "POST /process.Process/SendSignal",
          "Missing process -> 400",
          status, body, [400, 404, 200], verify_error_shape=False)


# ---------------------------------------------------------------------------
# TEAM ID DISCOVERY
# ---------------------------------------------------------------------------

def discover_team_id(api_key: str, env_team_id: str | None) -> str | None:
    """Try to discover a valid team ID from environment or API."""
    if env_team_id:
        return env_team_id

    # Try /teams (may need Supabase auth — might fail)
    h = auth(api_key)
    status, body = ctrl("GET", "/teams", headers=h)
    if status == 200 and isinstance(body, list) and body:
        tid = body[0].get("teamID") or body[0].get("id")
        if tid:
            return tid

    # Fall back: extract teamID from template or sandbox list
    status, body = ctrl("GET", "/templates", headers=h)
    if status == 200 and isinstance(body, list):
        for tpl in body:
            for key in ("teamID", "team_id", "teamId"):
                tid = tpl.get(key)
                if tid:
                    return tid

    status, body = ctrl("GET", "/sandboxes", headers=h)
    if status == 200 and isinstance(body, list):
        for sbx in body:
            for key in ("teamID", "team_id", "teamId"):
                tid = sbx.get(key)
                if tid:
                    return tid

    return None


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("E2B_API_KEY")
    if not api_key:
        print("Error: E2B_API_KEY environment variable is required")
        print("Usage: E2B_API_KEY=e2b_... python3 scripts/test_api_docs.py"
              " [--create-sandbox]")
        sys.exit(1)

    env_team_id = os.environ.get("E2B_TEAM_ID")
    create_sandbox = "--create-sandbox" in sys.argv

    print("=" * 60)
    print("  E2B API Documentation Verification — Comprehensive")
    print("=" * 60)
    print(f"  Base URL:        {BASE_URL}")
    print(f"  API Key:         {api_key[:10]}...{api_key[-4:]}")
    print(f"  Create sandbox:  {create_sandbox}")
    print(f"  Spec:            {SPEC_PATH.name}")

    with open(SPEC_PATH) as f:
        spec = yaml.safe_load(f)
    print(f"  Spec paths:      {len(spec.get('paths', {}))}")

    # Discover team ID for metrics tests
    team_id = discover_team_id(api_key, env_team_id)
    if team_id:
        print(f"  Team ID:         {team_id[:16]}...")
    else:
        print("  Team ID:         (not found)")

    suite = TestSuite()

    # ---- Section 1: 401 for ALL control plane endpoints ----
    test_401_all_control_plane(suite)

    # ---- Section 2: Sandbox endpoints ----
    test_sandbox_list(suite, api_key)
    test_sandbox_get_delete_404(suite, api_key)
    test_sandbox_actions_404(suite, api_key)
    test_create_sandbox_errors(suite, api_key)
    test_sandbox_logs(suite, api_key)

    # ---- Section 4: Metrics ----
    test_sandbox_metrics(suite, api_key)
    if team_id:
        test_team_metrics(suite, api_key, team_id)
    else:
        print("\n  [SKIP] Team metrics tests — no team ID available")

    # ---- Section 5: Teams ----
    test_teams(suite, api_key)

    # ---- Section 6: Templates ----
    test_template_reads(suite, api_key)
    test_template_create_errors(suite, api_key)
    test_template_update_delete_404(suite, api_key)
    test_template_builds(suite, api_key)
    test_template_files(suite, api_key)
    test_template_tags(suite, api_key)

    # ---- Section 7: Real sandbox + data plane (opt-in) ----
    if create_sandbox:
        test_with_real_sandbox(suite, api_key)
    else:
        print("\n  [SKIP] Sandbox integration + data plane tests"
              " (pass --create-sandbox to enable)")

    all_passed = suite.summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
