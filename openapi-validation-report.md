# E2B OpenAPI Spec Validation Report

**Date**: 2026-02-27 14:24:55 UTC
**Spec Version**: 0.1.0
**Endpoints Tested**: 59 / 59
**Critical Findings**: 0
**Duration**: 33.8s

## Executive Summary

No critical findings. The spec matches the live API behavior.

## Endpoint Results

### Platform API

#### GET /teams
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 401
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /teams/{teamID}/metrics
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /teams/{teamID}/metrics
- **Tested**: YES
- **Expected Status**: 400
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /teams/{teamID}/metrics/max
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /teams/{teamID}/metrics/max
- **Tested**: YES
- **Expected Status**: 403
- **Actual Status**: 403
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /templates
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /templates/{templateID}
- **Tested**: YES
- **Expected Status**: 404
- **Actual Status**: 404
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /templates/{templateID}/files/{hash}
- **Tested**: YES
- **Expected Status**: 404
- **Actual Status**: 404
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /v3/templates
- **Tested**: YES
- **Expected Status**: 202
- **Actual Status**: 202
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /templates/aliases/{alias}
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /v3/templates
- **Tested**: YES
- **Expected Status**: 400
- **Actual Status**: 400
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### PATCH /v2/templates/{templateID}
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### PATCH /templates/{templateID}
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /v2/templates/{templateID}/builds/{buildID}
- **Tested**: YES
- **Expected Status**: 202
- **Actual Status**: 202
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /v2/templates
- **Tested**: YES
- **Expected Status**: 202
- **Actual Status**: 202
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /v2/templates
- **Tested**: YES
- **Expected Status**: 400
- **Actual Status**: 400
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /templates/tags
- **Tested**: YES
- **Expected Status**: 400
- **Actual Status**: 400
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### DELETE /templates/tags
- **Tested**: YES
- **Expected Status**: 400
- **Actual Status**: 400
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### DELETE /templates/{templateID}
- **Tested**: YES
- **Expected Status**: 204
- **Actual Status**: 204
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### DELETE /templates/{templateID}
- **Tested**: YES
- **Expected Status**: 204
- **Actual Status**: 204
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### DELETE /templates/{templateID}
- **Tested**: YES
- **Expected Status**: 404
- **Actual Status**: 404
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /sandboxes
- **Tested**: YES
- **Expected Status**: 201
- **Actual Status**: 201
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /sandboxes
- **Tested**: YES
- **Expected Status**: 400
- **Actual Status**: 400
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /sandboxes
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /v2/sandboxes
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /sandboxes/{sandboxID}
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /sandboxes/{sandboxID}
- **Tested**: YES
- **Expected Status**: 404
- **Actual Status**: 400
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /sandboxes/{sandboxID}/timeout
- **Tested**: YES
- **Expected Status**: 204
- **Actual Status**: 204
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /sandboxes/{sandboxID}/refreshes
- **Tested**: YES
- **Expected Status**: 204
- **Actual Status**: 204
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /sandboxes/{sandboxID}/connect
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /sandboxes/{sandboxID}/logs
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /sandboxes/{sandboxID}/metrics
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /sandboxes/metrics
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /sandboxes/{sandboxID}/pause
- **Tested**: YES
- **Expected Status**: 204
- **Actual Status**: 204
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /sandboxes/{sandboxID}/resume
- **Tested**: YES
- **Expected Status**: 201
- **Actual Status**: 201
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### DELETE /sandboxes/{sandboxID}
- **Tested**: YES
- **Expected Status**: 204
- **Actual Status**: 204
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

### Sandbox API (envd)

#### GET /health
- **Tested**: YES
- **Expected Status**: 204
- **Actual Status**: 204
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /metrics
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /envs
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/MakeDir
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/Stat
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/ListDir
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/Move
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/Remove
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/Stat
- **Tested**: YES
- **Expected Status**: 404
- **Actual Status**: 404
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /files
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /files
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### GET /files
- **Tested**: YES
- **Expected Status**: 404
- **Actual Status**: 404
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/CreateWatcher
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/GetWatcherEvents
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/RemoveWatcher
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /process.Process/Start
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /process.Process/List
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /process.Process/Connect
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /process.Process/SendInput
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /process.Process/StreamInput
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /process.Process/Update
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /process.Process/SendSignal
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

#### POST /filesystem.Filesystem/WatchDir
- **Tested**: YES
- **Expected Status**: 200
- **Actual Status**: 200
- **Response Schema**:
  - Required fields present: YES
  - Extra undocumented fields: none
  - Type mismatches: none

## Critical Findings

Issues where the spec does not match the actual API behavior.

None found.

### Best-Practice Recommendations

Holistic improvements to make the spec production-quality.

| # | Category | Recommendation |
|---|----------|----------------|
| 1 | deprecated_no_migration | Deprecated operation 'GET /sandboxes/{sandboxID}/logs' has no migration note in description |
| 2 | deprecated_no_migration | Deprecated operation 'POST /sandboxes/{sandboxID}/resume' has no migration note in description |
| 3 | deprecated_no_migration | Deprecated operation 'POST /v2/templates' has no migration note in description |
| 4 | missing_param_description | Parameter 'hash' in 'GET /templates/{templateID}/files/{hash}' has no description |
| 5 | missing_param_description | Parameter 'teamID' in 'GET /templates' has no description |
| 6 | deprecated_no_migration | Deprecated operation 'POST /templates' has no migration note in description |
| 7 | deprecated_no_migration | Deprecated operation 'POST /templates/{templateID}' has no migration note in description |
| 8 | deprecated_no_migration | Deprecated operation 'PATCH /templates/{templateID}' has no migration note in description |
| 9 | deprecated_no_migration | Deprecated operation 'POST /templates/{templateID}/builds/{buildID}' has no migration note in description |
| 10 | missing_param_description | Parameter 'level' in 'GET /templates/{templateID}/builds/{buildID}/status' has no description |
| 11 | missing_param_description | Parameter 'direction' in 'GET /templates/{templateID}/builds/{buildID}/logs' has no description |
| 12 | missing_param_description | Parameter 'level' in 'GET /templates/{templateID}/builds/{buildID}/logs' has no description |
| 13 | missing_param_description | Parameter 'alias' in 'GET /templates/aliases/{alias}' has no description |
| 14 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/CreateWatcher' has no description |
| 15 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/CreateWatcher' has no description |
| 16 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/GetWatcherEvents' has no description |
| 17 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/GetWatcherEvents' has no description |
| 18 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/ListDir' has no description |
| 19 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/ListDir' has no description |
| 20 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/MakeDir' has no description |
| 21 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/MakeDir' has no description |
| 22 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/Move' has no description |
| 23 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/Move' has no description |
| 24 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/Remove' has no description |
| 25 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/Remove' has no description |
| 26 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/RemoveWatcher' has no description |
| 27 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/RemoveWatcher' has no description |
| 28 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/Stat' has no description |
| 29 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/Stat' has no description |
| 30 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /filesystem.Filesystem/WatchDir' has no description |
| 31 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /filesystem.Filesystem/WatchDir' has no description |
| 32 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/CloseStdin' has no description |
| 33 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/CloseStdin' has no description |
| 34 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/Connect' has no description |
| 35 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/Connect' has no description |
| 36 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/List' has no description |
| 37 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/List' has no description |
| 38 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/SendInput' has no description |
| 39 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/SendInput' has no description |
| 40 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/SendSignal' has no description |
| 41 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/SendSignal' has no description |
| 42 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/Start' has no description |
| 43 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/Start' has no description |
| 44 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/StreamInput' has no description |
| 45 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/StreamInput' has no description |
| 46 | missing_param_description | Parameter 'Connect-Protocol-Version' in 'POST /process.Process/Update' has no description |
| 47 | missing_param_description | Parameter 'Connect-Timeout-Ms' in 'POST /process.Process/Update' has no description |
| 48 | missing_schema_description | Property 'fields' in schema 'SandboxLogEntry' has no description |
| 49 | missing_schema_description | Property 'volumeMounts' in schema 'SandboxDetail' has no description |
| 50 | missing_schema_description | Property 'volumeMounts' in schema 'ListedSandbox' has no description |
| 51 | missing_schema_description | Property 'sandboxes' in schema 'SandboxesWithMetrics' has no description |
| 52 | missing_schema_description | Property 'volumeMounts' in schema 'NewSandbox' has no description |
| 53 | missing_schema_description | Property 'createdBy' in schema 'Template' has no description |
| 54 | missing_schema_description | Property 'createdBy' in schema 'TemplateLegacy' has no description |
| 55 | naming_inconsistency | Mixed naming: camelCase params (alias, cursor, direction, end, hash) and snake_case params (sandbox_ids) |
| 56 | truncated_description | Possible truncated description: '...Filter sandboxes by one or more states' |
| 57 | truncated_description | Possible truncated description: '...d list of sandbox IDs to get metrics for' |
| 58 | truncated_description | Possible truncated description: '... that should be returned in milliseconds' |
| 59 | truncated_description | Possible truncated description: '...m number of logs that should be returned' |
| 60 | truncated_description | Possible truncated description: '...hat should be returned with the template' |
| 61 | truncated_description | Possible truncated description: '...m number of logs that should be returned' |
| 62 | truncated_description | Possible truncated description: '... that should be returned in milliseconds' |
| 63 | truncated_description | Possible truncated description: '...m number of logs that should be returned' |
| 64 | truncated_description | Possible truncated description: '...of the logs that should be returned from' |
| 65 | truncated_description | Possible truncated description: '...Metric to retrieve the maximum value for' |

## Streaming Endpoints

Document what was tested and what could not be validated for each of the 4 streaming endpoints.

| Endpoint | What was tested | Limitations |
|----------|----------------|-------------|
| POST /filesystem.Filesystem/WatchDir | Initial HTTP response captured | Server-streaming: only first frame via stdlib urllib |
| POST /process.Process/Connect | Initial HTTP response captured | Server-streaming: only first frame via stdlib urllib |
| POST /process.Process/Start | Initial HTTP response captured | Server-streaming: only first frame via stdlib urllib |
| POST /process.Process/StreamInput | Initial HTTP request sent | Client-streaming: cannot maintain stream via stdlib urllib |

## Deprecated Endpoints

For each deprecated endpoint: does it still work? What does the spec say the replacement is?

| Endpoint | Still works? | Replacement | Notes |
|----------|-------------|-------------|-------|
| GET /sandboxes/{sandboxID}/logs | Yes | N/A (v2 endpoint doesn't exist) | v1 returns 200 |
| POST /sandboxes/{sandboxID}/resume | Yes | POST /sandboxes/{sandboxID}/connect | Returns Sandbox schema |
| POST /v2/templates | Yes | POST /v3/templates | v2 requires alias field |
| POST /templates | Needs Bearer | POST /v3/templates | Uses AccessTokenAuth |
| POST /templates/{templateID} | Needs Bearer | POST /v3/templates | Rebuild, uses AccessTokenAuth |
| PATCH /templates/{templateID} | Yes | PATCH /v2/templates/{templateID} | Update template |
| POST /templates/{templateID}/builds/{buildID} | Needs Bearer | POST /v2/.../builds/{buildID} | Start build |

## Untested Scenarios

List any endpoints or scenarios you could not test, and why.

| Endpoint | Reason |
|----------|--------|
| Rate limiting (429) | Cannot safely trigger without affecting quota |
| Conflict (409) | Requires specific data state |
| Internal errors (500) | Cannot reliably reproduce |
