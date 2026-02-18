Set up an environment and collection for testing the E2B API. I'll add endpoints one by one — guide me through each.

## API Overview

E2B has **two API planes** with different base URLs and auth:

### 1. Control Plane — `https://api.e2b.app`
- **Auth:** `X-API-Key` header (value: `{{API_KEY}}`)
- **Endpoints:** Sandbox CRUD, templates, metrics, teams
- All requests/responses are `application/json`

### 2. Data Plane — `https://49982-{{SANDBOX_ID}}.e2b.app`
- **Auth:** `X-Access-Token` header (value: `{{ACCESS_TOKEN}}`)
- **Base URL is dynamic** — each sandbox has its own subdomain
- **Two sub-types:**
  - **REST endpoints:** `GET /files`, `POST /files` (multipart upload)
  - **Connect RPC endpoints:** All filesystem and process operations use `POST` to paths like `/filesystem.Filesystem/ListDir` and `/process.Process/Start` with `Content-Type: application/json` bodies

## Environment Variables to Create

| Variable | Type | Description |
|----------|------|-------------|
| `API_KEY` | secret | E2B API key (starts with `e2b_`) |
| `BASE_URL` | default: `https://api.e2b.app` | Control plane base URL |
| `SANDBOX_ID` | empty | Filled after creating a sandbox |
| `ACCESS_TOKEN` | secret, empty | Filled after creating a sandbox (`envdAccessToken` from response) |
| `SANDBOX_BASE_URL` | empty | Computed as `https://49982-{{SANDBOX_ID}}.e2b.app` |
| `TEMPLATE_ID` | default: `base` | Template to use for sandbox creation |
| `TEAM_ID` | empty | Team ID for metrics endpoints |

## Collection Structure (folders)

```
E2B API/
├── Sandboxes/          — CRUD, pause, resume, connect, timeout, refreshes, logs
├── Templates/          — CRUD, builds, tags, aliases, file upload links
├── Metrics/            — Sandbox metrics, team metrics
├── Sandbox Filesystem/ — File upload/download + Connect RPC filesystem ops
└── Sandbox Process/    — Connect RPC process ops (start, list, signal, input)
```

## Key Workflow

The typical testing flow is:
1. `POST {{BASE_URL}}/sandboxes` with `{"templateID": "{{TEMPLATE_ID}}"}` — returns `sandboxID` and `envdAccessToken`
2. Save `sandboxID` → `SANDBOX_ID` and `envdAccessToken` → `ACCESS_TOKEN` (use a post-response script)
3. Now data plane endpoints work at `https://49982-{{SANDBOX_ID}}.e2b.app`
4. Test filesystem/process endpoints against the live sandbox
5. Clean up: `DELETE {{BASE_URL}}/sandboxes/{{SANDBOX_ID}}`

## Post-response script for "Create Sandbox"

After `POST /sandboxes` succeeds, auto-populate variables:
```js
const body = pm.response.json();
pm.environment.set("SANDBOX_ID", body.sandboxID);
pm.environment.set("ACCESS_TOKEN", body.envdAccessToken);
pm.environment.set("SANDBOX_BASE_URL", "https://49982-" + body.sandboxID + ".e2b.app");
```

## Connect RPC Convention

Filesystem and process endpoints use a gRPC-compatible HTTP protocol:
- Method: always `POST`
- URL: `{{SANDBOX_BASE_URL}}/filesystem.Filesystem/ListDir` (or `/process.Process/Start`, etc.)
- Headers: `Content-Type: application/json` + `X-Access-Token: {{ACCESS_TOKEN}}`
- Body: JSON object (e.g., `{"path": "/home/user", "depth": 1}`)
- Response: JSON object

These are NOT standard REST — they follow the Connect RPC protocol where the service and method name are in the URL path.

## Guide Me

As I add each endpoint, help me set the correct method, URL, headers, body, and any test scripts. Warn me if an endpoint is destructive (DELETE sandbox, remove files, send SIGKILL). I'll go group by group.
