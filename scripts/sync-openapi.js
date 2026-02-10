#!/usr/bin/env node

/**
 * OpenAPI Spec Sync Script
 *
 * Generates the public API reference by merging and polishing specs from the
 * local infra repository clone. Reads the REST API spec and Sandbox API spec,
 * filters admin/internal endpoints, applies documentation polish, and outputs
 * a single merged spec for Mintlify.
 *
 * Usage:
 *   node scripts/sync-openapi.js [--infra-path /path/to/infra]
 *
 * By default, looks for the infra repo at ../infra relative to this repo.
 * The expanded envd.yaml should include all sandbox endpoints (filesystem, process).
 */

const fs = require('fs');
const path = require('path');

// Try to load js-yaml, install if not available
let yaml;
try {
  yaml = require('js-yaml');
} catch (e) {
  console.log('Installing js-yaml...');
  const { execSync } = require('child_process');
  execSync('npm install js-yaml', { stdio: 'inherit' });
  yaml = require('js-yaml');
}

// === CONFIGURATION ===

// Parse --infra-path argument
let infraPath = path.resolve(__dirname, '../../infra');
const infraArgIdx = process.argv.indexOf('--infra-path');
if (infraArgIdx !== -1 && process.argv[infraArgIdx + 1]) {
  infraPath = path.resolve(process.argv[infraArgIdx + 1]);
}

const CONFIG = {
  output: 'openapi-public-edited.yml',

  restApi: {
    source: path.join(infraPath, 'spec/openapi.yml'),
    excludePaths: [
      '/access-tokens',
      '/access-tokens/{accessTokenID}',
      '/admin/teams/{teamID}/sandboxes/kill',
      '/api-keys',
      '/api-keys/{apiKeyID}',
      '/health',
      '/nodes',
      '/nodes/{nodeID}',
    ],
    // Paths to include even when they don't have ApiKeyAuth in the source spec
    // (they use AccessTokenAuth in the backend but should still appear in public docs)
    forceIncludePaths: new Set([
      '/teams',
      '/templates',           // POST (legacy, deprecated)
      '/templates/{templateID}', // POST (legacy rebuild, deprecated)
      '/templates/{templateID}/builds/{buildID}', // POST (legacy build start, deprecated)
    ]),
    excludeSecuritySchemes: [
      'Supabase1TokenAuth',
      'Supabase2TeamAuth',
      'AdminTokenAuth',
    ],
    // Parameters only used by admin/internal endpoints
    excludeParameters: new Set(['nodeID', 'apiKeyID', 'accessTokenID', 'tag']),
    // Schemas only used by admin/internal endpoints
    excludeSchemas: [
      'AdminSandboxKillResult',
      'CreatedAccessToken',
      'CreatedTeamAPIKey',
      'DiskMetrics',
      'IdentifierMaskingDetails',
      'MachineInfo',
      'NewAccessToken',
      'NewTeamAPIKey',
      'Node',
      'NodeDetail',
      'NodeMetrics',
      'NodeStatus',
      'NodeStatusChange',
      'TeamAPIKey',
      'UpdateTeamAPIKey',
    ],
  },

  sandboxApi: {
    source: path.join(infraPath, 'packages/envd/spec/envd.yaml'),
    excludePaths: ['/health', '/metrics', '/envs'],
    tagRenames: {
      files: 'Sandbox Filesystem',
      filesystem: 'Sandbox Filesystem',
      process: 'Sandbox Process',
    },
  },
};

// === DOCUMENTATION POLISH ===
// Rich descriptions, summaries, operationIds, and examples that transform
// the raw backend spec into user-friendly API documentation.

const INFO = {
  version: '0.1.0',
  title: 'E2B API',
  description: `The E2B API allows you to programmatically create, manage, and interact with cloud sandboxes - secure, isolated environments for running code.

## Overview

The API is split into two parts:

### Control Plane API (\`api.e2b.app\`)
Use this API to manage the lifecycle of sandboxes and templates:
- **Sandboxes**: Create, list, pause, resume, and terminate sandboxes
- **Templates**: Build and manage custom sandbox templates
- **Metrics**: Monitor usage and resource consumption

### Data Plane API (\`{port}-{sandboxId}.e2b.app\`)
Use this API to interact with a running sandbox:
- **Files**: Upload and download files
- **Filesystem**: Create directories, list contents, move and delete files
- **Processes**: Start, monitor, and control processes

## Authentication

### Control Plane (X-API-Key)
All Control Plane endpoints require your API key in the \`X-API-Key\` header.
Get your API key from the [E2B Dashboard](https://e2b.dev/dashboard?tab=keys).

\`\`\`bash
curl -H "X-API-Key: e2b_YOUR_API_KEY" https://api.e2b.app/sandboxes
\`\`\`

### Data Plane (X-Access-Token)
Data Plane endpoints require the \`X-Access-Token\` header with the access token
returned when you create a sandbox.

\`\`\`bash
# 1. Create a sandbox (returns sandboxId and envdAccessToken)
curl -X POST -H "X-API-Key: e2b_YOUR_API_KEY" \\
  -d '{"templateID": "base"}' \\
  https://api.e2b.app/sandboxes

# 2. Use the token to interact with the sandbox
curl -H "X-Access-Token: YOUR_ACCESS_TOKEN" \\
  https://49982-YOUR_SANDBOX_ID.e2b.app/files?path=/home/user/file.txt
\`\`\`

## Quick Start

1. **Create a sandbox** from a template using \`POST /sandboxes\`
2. **Get the access token** from the response (\`envdAccessToken\`)
3. **Interact with the sandbox** using the Data Plane API
4. **Clean up** by deleting the sandbox with \`DELETE /sandboxes/{sandboxID}\`

## Rate Limits

API requests are rate limited. Contact support if you need higher limits.

## SDKs

We provide official SDKs for Python, JavaScript/TypeScript, and Go.
See [SDK Reference](https://e2b.dev/docs/sdk-reference) for details.`,
};

const TAGS = [
  {
    name: 'Sandboxes',
    description: `Create and manage sandbox instances. Sandboxes are isolated cloud environments
where you can safely run code, install packages, and execute processes.

**Common workflows:**
- Create a sandbox → Run code → Delete sandbox
- Create a sandbox → Pause → Resume later → Delete
- List running sandboxes → Get metrics → Clean up idle ones`,
  },
  {
    name: 'Templates',
    description: `Build and manage custom templates. Templates are pre-configured sandbox images
with your preferred tools, packages, and configurations pre-installed.

**Use templates to:**
- Speed up sandbox creation by pre-installing dependencies
- Ensure consistent environments across sandboxes
- Share configurations across your team`,
  },
  {
    name: 'Metrics',
    description: `Monitor resource usage and track sandbox activity. Use metrics to understand
your usage patterns and optimize costs.`,
  },
  {
    name: 'Teams',
    description: `List and manage your teams. Teams are organizational units that own
sandboxes, templates, and API keys.`,
  },
  {
    name: 'Sandbox Filesystem',
    description: `Perform filesystem operations inside a running sandbox. Create directories,
list contents, move files, delete files, and watch for changes.

**Base URL:** \`https://{port}-{sandboxId}.e2b.app\`

These endpoints use Connect RPC protocol over HTTP.`,
  },
  {
    name: 'Sandbox Process',
    description: `Start and manage processes inside a running sandbox. Execute commands,
stream output, send input, and control running processes.

**Base URL:** \`https://{port}-{sandboxId}.e2b.app\`

These endpoints use Connect RPC protocol over HTTP.`,
  },
];

// Sandbox endpoint polish (applied during sandbox processing)
const SANDBOX_ENDPOINT_POLISH = {
  'POST /init': {
    summary: 'Initialize sandbox',
    description: `Initializes a sandbox after creation. Syncs environment variables and metadata.`,
    operationId: 'initSandbox',
    tags: ['Sandboxes'],
  },
};

// Per-endpoint documentation polish for REST API endpoints
// Keys are "METHOD /path", values override properties on the operation
const ENDPOINT_POLISH = {
  'GET /sandboxes': {
    summary: 'List running sandboxes',
    description: `Returns a list of all currently running sandboxes for your team.
Use the \`metadata\` parameter to filter sandboxes by custom metadata.

**Note:** This endpoint only returns running sandboxes. Paused sandboxes
are not included. Use \`GET /v2/sandboxes\` with state filter for more options.`,
    operationId: 'listSandboxes',
    tags: ['Sandboxes'],
    responseOverrides: {
      200: {
        description: 'List of running sandboxes',
        example: [
          {
            sandboxID: 'sandbox-abc123xyz',
            templateID: 'base',
            alias: 'my-python-env',
            clientID: 'sandbox-abc123xyz',
            startedAt: '2024-01-15T10:30:00Z',
            endAt: '2024-01-15T10:45:00Z',
            cpuCount: 2,
            memoryMB: 512,
            metadata: { user: 'user-123', project: 'demo' },
          },
        ],
      },
    },
    paramOverrides: {
      metadata: {
        description: 'Filter sandboxes by metadata. Format: key=value&key2=value2\nEach key and value must be URL encoded.',
        example: 'user=user-123&project=demo',
      },
    },
  },
  'POST /sandboxes': {
    summary: 'Create a sandbox',
    description: `Creates a new sandbox from the specified template. The sandbox starts
immediately and is ready to use within a few seconds.

**Returns:**
- \`sandboxID\`: Use this to identify the sandbox in subsequent API calls
- \`envdAccessToken\`: Use this as \`X-Access-Token\` for Data Plane API calls`,
    operationId: 'createSandbox',
    tags: ['Sandboxes'],
    requestExample: {
      templateID: 'base',
      timeout: 300,
      metadata: { user: 'user-123', project: 'code-review' },
    },
    responseOverrides: {
      201: {
        description: 'Sandbox created successfully',
        example: {
          sandboxID: 'sandbox-abc123xyz',
          templateID: 'base',
          clientID: 'sandbox-abc123xyz',
          envdAccessToken: 'eyJhbGciOiJIUzI1NiIs...',
          envdVersion: '0.1.0',
        },
      },
    },
  },
  'GET /sandboxes/{sandboxID}': {
    summary: 'Get sandbox details',
    description: `Returns detailed information about a specific sandbox, including its
current state, resource allocation, and metadata.`,
    operationId: 'getSandbox',
    tags: ['Sandboxes'],
  },
  'DELETE /sandboxes/{sandboxID}': {
    summary: 'Terminate a sandbox',
    description: `Immediately terminates and deletes a sandbox. All data in the sandbox
is permanently lost.

**Warning:** This action cannot be undone. If you want to preserve the
sandbox state for later, use \`POST /sandboxes/{sandboxID}/pause\` instead.`,
    operationId: 'deleteSandbox',
    tags: ['Sandboxes'],
    responseOverrides: {
      204: { description: 'Sandbox terminated successfully' },
    },
  },
  'POST /sandboxes/{sandboxID}/pause': {
    summary: 'Pause a sandbox',
    description: `Pauses a running sandbox. The sandbox state is preserved and can be
resumed later with \`POST /sandboxes/{sandboxID}/connect\`.

**Benefits of pausing:**
- No compute charges while paused
- State is preserved (files, installed packages, etc.)
- Resume in seconds instead of creating a new sandbox

**Limitations:**
- Running processes are stopped
- Network connections are closed
- Paused sandboxes have a maximum retention period`,
    operationId: 'pauseSandbox',
    tags: ['Sandboxes'],
    responseOverrides: {
      204: { description: 'Sandbox paused successfully' },
    },
  },
  'POST /sandboxes/{sandboxID}/resume': {
    summary: 'Resume a paused sandbox',
    description: `Resumes a previously paused sandbox.

**Deprecated:** Use \`POST /sandboxes/{sandboxID}/connect\` instead,
which handles both running and paused sandboxes.`,
    operationId: 'resumeSandbox',
    tags: ['Sandboxes'],
  },
  'POST /sandboxes/{sandboxID}/connect': {
    summary: 'Connect to or resume a sandbox',
    description: `Returns sandbox connection details. If the sandbox is paused, it will
be automatically resumed.

Use this endpoint to:
- Resume a paused sandbox
- Get connection details for a running sandbox
- Extend the sandbox timeout

**Note:** The timeout is extended from the current time, not added to
the existing timeout.`,
    operationId: 'connectSandbox',
    tags: ['Sandboxes'],
  },
  'POST /sandboxes/{sandboxID}/timeout': {
    summary: 'Set sandbox timeout',
    description: `Sets a new timeout for the sandbox. The sandbox will automatically
terminate after the specified number of seconds from now.

**Note:** This replaces any existing timeout. Each call resets the
countdown from the current time.`,
    operationId: 'setSandboxTimeout',
    tags: ['Sandboxes'],
    responseOverrides: {
      204: { description: 'Timeout updated successfully' },
    },
  },
  'POST /sandboxes/{sandboxID}/refreshes': {
    summary: 'Extend sandbox lifetime',
    description: `Extends the sandbox lifetime by the specified duration. Unlike
\`/timeout\`, this adds time to the existing expiration.`,
    operationId: 'refreshSandbox',
    tags: ['Sandboxes'],
    responseOverrides: {
      204: { description: 'Sandbox lifetime extended' },
    },
  },
  'GET /v2/sandboxes': {
    summary: 'List all sandboxes (v2)',
    description: `Returns all sandboxes, including paused ones. Supports filtering by
state and metadata, and pagination.`,
    operationId: 'listSandboxesV2',
    tags: ['Sandboxes'],
    responseOverrides: {
      200: { description: 'List of sandboxes' },
    },
  },
  'GET /sandboxes/metrics': {
    summary: 'Get metrics for multiple sandboxes',
    description: `Returns the latest metrics for a batch of sandboxes. Useful for
monitoring dashboards.`,
    operationId: 'getSandboxesMetrics',
    tags: ['Metrics'],
    responseOverrides: {
      200: { description: 'Metrics per sandbox' },
    },
    paramOverrides: {
      sandbox_ids: {
        description: 'Comma-separated list of sandbox IDs (max 100)',
      },
    },
  },
  'GET /sandboxes/{sandboxID}/logs': {
    summary: 'Get sandbox logs (legacy)',
    description: `Returns system logs from the sandbox.

**Deprecated:** Use \`GET /v2/sandboxes/{sandboxID}/logs\` instead.`,
    operationId: 'getSandboxLogs',
    tags: ['Sandboxes'],
    responseOverrides: {
      200: { description: 'Sandbox logs' },
    },
    paramOverrides: {
      start: { description: 'Start timestamp in milliseconds (Unix epoch)' },
      limit: { description: 'Maximum number of log entries to return' },
    },
  },
  'GET /v2/sandboxes/{sandboxID}/logs': {
    summary: 'Get sandbox logs',
    description: `Returns system logs from the sandbox. These include sandbox startup logs
and system-level events. Supports pagination and filtering.`,
    operationId: 'getSandboxLogsV2',
    tags: ['Sandboxes'],
    responseOverrides: {
      200: { description: 'Sandbox logs' },
    },
    paramOverrides: {
      cursor: { description: 'Starting timestamp in milliseconds (Unix epoch)' },
      limit: { description: 'Maximum number of log entries to return' },
    },
  },
  'GET /sandboxes/{sandboxID}/metrics': {
    summary: 'Get sandbox metrics',
    description: `Returns resource usage metrics (CPU, memory, disk) for a specific sandbox
over a time range.`,
    operationId: 'getSandboxMetrics',
    tags: ['Metrics'],
    responseOverrides: {
      200: { description: 'Sandbox metrics' },
    },
    paramOverrides: {
      start: { description: 'Start timestamp in seconds (Unix epoch)' },
      end: { description: 'End timestamp in seconds (Unix epoch)' },
    },
  },
  'GET /teams/{teamID}/metrics': {
    summary: 'Get team metrics',
    description: `Returns usage metrics for your team over a time range, including
concurrent sandbox count and sandbox start rate.`,
    operationId: 'getTeamMetrics',
    tags: ['Metrics'],
    responseOverrides: {
      200: { description: 'Team metrics' },
    },
  },
  'GET /teams/{teamID}/metrics/max': {
    summary: 'Get max team metrics',
    description: `Returns the maximum value of a specific metric for your team
over a time range.`,
    operationId: 'getTeamMetricsMax',
    tags: ['Metrics'],
    responseOverrides: {
      200: { description: 'Maximum metric value' },
    },
    paramOverrides: {
      metric: { description: 'Which metric to get the maximum value for' },
    },
  },
  'GET /teams': {
    summary: 'List teams',
    description: 'Returns all teams accessible to the authenticated user.',
    operationId: 'listTeams',
    tags: ['Teams'],
  },
  'GET /templates': {
    summary: 'List templates',
    description: `Returns all templates accessible to your team, including both custom
templates you've created and public templates.`,
    operationId: 'listTemplates',
    tags: ['Templates'],
  },
  'POST /templates': {
    summary: 'Create a new template (legacy)',
    description: `Creates a new template from a Dockerfile.

**Deprecated:** Use \`POST /v3/templates\` instead.`,
    operationId: 'createTemplateLegacy',
    tags: ['Templates'],
  },
  'GET /templates/{templateID}': {
    summary: 'Get template details',
    description: 'Returns detailed information about a template, including all its builds.',
    operationId: 'getTemplate',
    tags: ['Templates'],
    responseOverrides: {
      200: { description: 'Template details with builds' },
    },
  },
  'POST /templates/{templateID}': {
    summary: 'Rebuild a template (legacy)',
    description: `Triggers a rebuild of an existing template from a Dockerfile.

**Deprecated:** Use \`POST /v3/templates\` instead.`,
    operationId: 'rebuildTemplateLegacy',
    tags: ['Templates'],
  },
  'DELETE /templates/{templateID}': {
    summary: 'Delete a template',
    description: `Permanently deletes a template and all its builds.

**Warning:** This action cannot be undone. Existing sandboxes created
from this template will continue to work, but no new sandboxes can be
created from it.`,
    operationId: 'deleteTemplate',
    tags: ['Templates'],
  },
  'PATCH /templates/{templateID}': {
    summary: 'Update template',
    description: `Updates template properties (e.g., public/private visibility).

**Deprecated:** Use \`PATCH /v2/templates/{templateID}\` instead.`,
    operationId: 'updateTemplate',
    tags: ['Templates'],
    responseOverrides: {
      200: { description: 'Template updated' },
    },
  },
  'POST /v3/templates': {
    summary: 'Create a new template',
    description: `Creates a new template and initiates a build. Returns the template ID
and build ID to track the build progress.`,
    operationId: 'createTemplateV3',
    tags: ['Templates'],
    responseOverrides: {
      202: { description: 'Build started' },
    },
  },
  'POST /v2/templates': {
    summary: 'Create a new template (v2)',
    description: `Creates a new template.

**Deprecated:** Use \`POST /v3/templates\` instead.`,
    operationId: 'createTemplateV2',
    tags: ['Templates'],
    responseOverrides: {
      202: { description: 'Build started' },
    },
  },
  'PATCH /v2/templates/{templateID}': {
    summary: 'Update template (v2)',
    description: 'Updates template properties such as visibility (public/private).',
    operationId: 'updateTemplateV2',
    tags: ['Templates'],
    responseOverrides: {
      200: { description: 'Template updated' },
    },
  },
  'GET /templates/{templateID}/files/{hash}': {
    summary: 'Get build file upload link',
    description: `Returns a pre-signed upload URL for uploading build layer files
as a tar archive.`,
    operationId: 'getTemplateFileUploadLink',
    tags: ['Templates'],
    responseOverrides: {
      201: { description: 'Upload link' },
    },
    paramOverrides: {
      hash: { description: 'SHA256 hash of the tar file' },
    },
  },
  'POST /templates/{templateID}/builds/{buildID}': {
    summary: 'Start a template build (legacy)',
    description: `Starts a previously created template build.

**Deprecated:** Use \`POST /v2/templates/{templateID}/builds/{buildID}\` instead.`,
    operationId: 'startTemplateBuildLegacy',
    tags: ['Templates'],
  },
  'POST /v2/templates/{templateID}/builds/{buildID}': {
    summary: 'Start a template build',
    description: `Triggers the build process for a template. The build must have been
previously created and files uploaded.`,
    operationId: 'startTemplateBuild',
    tags: ['Templates'],
    responseOverrides: {
      202: { description: 'Build started' },
    },
  },
  'GET /templates/{templateID}/builds/{buildID}/status': {
    summary: 'Get build status',
    description: 'Returns the current status and logs for a template build.',
    operationId: 'getTemplateBuildStatus',
    tags: ['Templates'],
    responseOverrides: {
      200: { description: 'Build status and logs' },
    },
  },
  'GET /templates/{templateID}/builds/{buildID}/logs': {
    summary: 'Get build logs',
    description: 'Returns logs from a template build with pagination and filtering options.',
    operationId: 'getTemplateBuildLogs',
    tags: ['Templates'],
  },
  'POST /templates/tags': {
    summary: 'Assign tags to a template build',
    description: `Assigns one or more tags to a specific template build. Tags can be used
to version and identify specific builds (e.g., "latest", "v1.0").`,
    operationId: 'assignTemplateTags',
    tags: ['Templates'],
    responseOverrides: {
      201: { description: 'Tags assigned' },
    },
  },
  'DELETE /templates/tags': {
    summary: 'Delete tags from templates',
    description: 'Removes tags from template builds.',
    operationId: 'deleteTemplateTags',
    tags: ['Templates'],
    responseOverrides: {
      204: { description: 'Tags deleted' },
    },
  },
  'GET /templates/aliases/{alias}': {
    summary: 'Check template by alias',
    description: 'Checks if a template with the given alias exists and returns its ID.',
    operationId: 'getTemplateByAlias',
    tags: ['Templates'],
    responseOverrides: {
      200: { description: 'Template found' },
    },
    paramOverrides: {
      alias: { description: 'Template alias to look up' },
    },
  },
};

// Schema descriptions and examples for polishing raw schemas
const SCHEMA_POLISH = {
  Error: {
    description: 'Error response returned when a request fails',
    properties: {
      code: { description: 'HTTP status code', example: 400 },
      message: { description: 'Human-readable error message', example: 'Invalid request parameters' },
    },
  },
  NewSandbox: {
    description: 'Request body for creating a new sandbox',
    properties: {
      templateID: {
        description: 'ID of the template to use. Can be a built-in template (`base`, `python`, `node`) or a custom template ID.',
        example: 'base',
      },
      timeout: {
        description: 'How long the sandbox should stay alive in seconds, measured from creation time. The sandbox will automatically terminate after this duration unless extended. Maximum: 24 hours (86400 seconds).',
        example: 300,
      },
      autoPause: {
        description: 'If true, the sandbox will automatically pause instead of terminating when the timeout expires.',
        example: true,
      },
      metadata: {
        description: 'Custom key-value metadata to attach to the sandbox. Useful for filtering and organizing sandboxes.',
        example: { user: 'user-123', project: 'code-review', environment: 'staging' },
      },
      envVars: {
        description: 'Environment variables to set in the sandbox.',
        example: { NODE_ENV: 'production', API_URL: 'https://api.example.com' },
      },
    },
  },
  Sandbox: {
    description: 'A sandbox instance that was just created',
    properties: {
      sandboxID: { description: 'Unique identifier of the sandbox', example: 'sandbox-abc123xyz' },
      templateID: { description: 'ID of the template this sandbox was created from', example: 'base' },
      envdAccessToken: {
        description: 'Access token for Data Plane API calls. Use this as the `X-Access-Token` header when calling sandbox endpoints.',
        example: 'eyJhbGciOiJIUzI1NiIs...',
      },
      envdVersion: { description: 'Version of the sandbox runtime', example: '0.1.0' },
      domain: { description: 'Base domain for accessing the sandbox', example: 'e2b.app' },
    },
  },
  SandboxDetail: {
    description: 'Detailed information about a sandbox',
    properties: {
      sandboxID: { description: 'Unique identifier of the sandbox', example: 'sandbox-abc123xyz' },
      templateID: { description: 'ID of the template this sandbox was created from', example: 'base' },
      alias: { description: 'Human-readable alias for the template', example: 'my-python-template' },
      startedAt: { description: 'When the sandbox was created', example: '2024-01-15T10:30:00Z' },
      endAt: { description: 'When the sandbox will automatically terminate (can be extended)', example: '2024-01-15T10:45:00Z' },
      cpuCount: { description: 'Number of CPU cores allocated', example: 2 },
      memoryMB: { description: 'Memory allocated in megabytes', example: 512 },
      diskSizeMB: { description: 'Disk space allocated in megabytes', example: 1024 },
      envdAccessToken: { description: 'Access token for Data Plane API calls' },
    },
  },
  ListedSandbox: {
    description: 'Summary information about a sandbox in a list',
  },
  Template: {
    description: 'A sandbox template with pre-installed tools and configurations',
    properties: {
      templateID: { description: 'Unique identifier of the template', example: 'tpl-abc123' },
      buildID: { description: 'ID of the current (latest successful) build', example: '550e8400-e29b-41d4-a716-446655440000' },
      names: { description: 'Human-readable names/aliases for the template', example: ['my-python-env', 'team/python-ml'] },
      cpuCount: { description: 'Default CPU cores for sandboxes', example: 2 },
      memoryMB: { description: 'Default memory in MB', example: 512 },
      diskSizeMB: { description: 'Default disk size in MB', example: 1024 },
      spawnCount: { description: 'Total number of sandboxes created from this template', example: 1542 },
    },
  },
  SandboxMetric: {
    description: 'Resource usage metrics for a sandbox at a point in time',
    properties: {
      timestampUnix: { description: 'Unix timestamp (seconds since epoch)', example: 1705315800 },
      cpuCount: { description: 'Number of CPU cores', example: 2 },
      cpuUsedPct: { description: 'CPU usage as a percentage (0-100 per core, so max is cpuCount * 100)', example: 45.5 },
      memUsed: { description: 'Memory used in bytes', example: 268435456 },
      memTotal: { description: 'Total memory available in bytes', example: 536870912 },
      diskUsed: { description: 'Disk space used in bytes', example: 104857600 },
      diskTotal: { description: 'Total disk space in bytes', example: 1073741824 },
    },
  },
  Team: {
    description: 'A team in the E2B platform',
  },
};

// Response examples for polishing
const RESPONSE_EXAMPLES = {
  400: { code: 400, message: 'Invalid request: templateID is required' },
  401: { code: 401, message: 'Invalid API key' },
  403: { code: 403, message: 'Access denied' },
  404: { code: 404, message: 'Sandbox not found' },
  409: { code: 409, message: 'Sandbox is already paused' },
  500: { code: 500, message: 'Internal server error' },
};

const RESPONSE_DESCRIPTIONS = {
  400: 'Bad Request - The request was malformed or missing required parameters',
  401: 'Unauthorized - Invalid or missing API key',
  403: "Forbidden - You don't have permission to access this resource",
  404: "Not Found - The requested resource doesn't exist",
  409: 'Conflict - The request conflicts with the current state',
  500: 'Internal Server Error - Something went wrong on our end',
};

// Parameter polish
const PARAM_POLISH = {
  templateID: {
    description: 'Unique identifier of the template (e.g., `base`, `python`, or a custom template ID)',
    example: 'base',
  },
  buildID: {
    description: 'Unique identifier of a template build (UUID format)',
    example: '550e8400-e29b-41d4-a716-446655440000',
  },
  sandboxID: {
    description: 'Unique identifier of the sandbox',
    example: 'sandbox-abc123',
  },
  teamID: {
    description: 'Unique identifier of your team',
  },
  paginationLimit: {
    description: 'Maximum number of items to return per page (1-100)',
    example: 50,
  },
  paginationNextToken: {
    description: 'Cursor for pagination. Use the value from the previous response to get the next page.',
  },
};

// Sandbox server definition
const SANDBOX_SERVER = {
  url: 'https://{port}-{sandboxId}.e2b.app',
  description: 'Sandbox Data Plane API',
  variables: {
    port: {
      default: '49982',
      description: 'API port (always 49982)',
    },
    sandboxId: {
      default: 'your-sandbox-id',
      description: 'Your sandbox ID from the create response',
    },
  },
};

// Simple $ref schemas to inline (these are just type aliases in the infra spec)
const INLINE_REFS = {
  CPUCount: { type: 'integer', format: 'int32', minimum: 1 },
  MemoryMB: { type: 'integer', format: 'int32', minimum: 128 },
  DiskSizeMB: { type: 'integer', format: 'int32', minimum: 0 },
  EnvdVersion: { type: 'string' },
  SandboxState: { type: 'string', enum: ['running', 'paused'] },
  SandboxMetadata: { type: 'object', additionalProperties: { type: 'string' } },
  EnvVars: { type: 'object', additionalProperties: { type: 'string' } },
};

// === UTILITY FUNCTIONS ===

function loadYaml(filepath) {
  console.log(`Loading: ${filepath}`);
  const content = fs.readFileSync(filepath, 'utf8');
  return yaml.load(content);
}

/**
 * Reorder OpenAPI operation properties to the conventional order.
 * This ensures consistent, readable output regardless of when properties are set.
 */
const OPERATION_KEY_ORDER = [
  'summary', 'description', 'operationId', 'deprecated', 'tags',
  'security', 'parameters', 'requestBody', 'responses',
  'callbacks', 'servers',
];

function reorderOperationKeys(spec) {
  if (!spec?.paths) return spec;
  for (const methods of Object.values(spec.paths)) {
    for (const [key, value] of Object.entries(methods)) {
      if (key === 'servers' || key === 'parameters' || !value || typeof value !== 'object') continue;
      // This is an operation object
      const ordered = {};
      for (const k of OPERATION_KEY_ORDER) {
        if (value[k] !== undefined) ordered[k] = value[k];
      }
      // Add any remaining keys not in the ordered list
      for (const k of Object.keys(value)) {
        if (!(k in ordered)) ordered[k] = value[k];
      }
      methods[key] = ordered;
    }
  }
  return spec;
}

function saveYaml(filename, data) {
  const outputPath = path.join(process.cwd(), filename);
  const content = yaml.dump(data, {
    lineWidth: -1,
    noRefs: true,
    quotingType: '"',
    forceQuotes: false,
    sortKeys: false,
  });
  fs.writeFileSync(outputPath, content);
  console.log(`Saved: ${outputPath}`);
}

// === REST API PROCESSING ===

function processRestApi(spec) {
  console.log('\n=== Processing REST API ===\n');

  const filteredPaths = {};

  for (const [pathStr, methods] of Object.entries(spec.paths || {})) {
    // Skip excluded paths
    if (CONFIG.restApi.excludePaths.includes(pathStr)) {
      continue;
    }

    const filteredMethods = {};
    for (const [method, operation] of Object.entries(methods)) {
      // Skip non-operation properties
      if (!operation || typeof operation !== 'object' || !operation.responses) continue;

      // Only keep endpoints accessible via ApiKeyAuth, unless force-included
      const hasApiKeyAuth = operation.security?.some(secObj =>
        Object.keys(secObj).includes('ApiKeyAuth')
      );
      const isForceIncluded = CONFIG.restApi.forceIncludePaths.has(pathStr);
      if (!hasApiKeyAuth && operation.security && !isForceIncluded) continue;

      // Clean up security - only keep ApiKeyAuth
      if (operation.security) {
        operation.security = [{ ApiKeyAuth: [] }];
      }

      // Apply documentation polish
      const polishKey = `${method.toUpperCase()} ${pathStr}`;
      const polish = ENDPOINT_POLISH[polishKey];
      if (polish) {
        if (polish.summary) operation.summary = polish.summary;
        if (polish.description) operation.description = polish.description;
        if (polish.operationId) operation.operationId = polish.operationId;
        if (polish.tags) operation.tags = polish.tags;

        // Apply response description overrides
        if (polish.responseOverrides && operation.responses) {
          for (const [code, overrides] of Object.entries(polish.responseOverrides)) {
            if (operation.responses[String(code)]) {
              if (overrides.description) {
                operation.responses[String(code)].description = overrides.description;
              }
              if (overrides.example && operation.responses[String(code)].content?.['application/json']) {
                operation.responses[String(code)].content['application/json'].example = overrides.example;
              }
            }
          }
        }

        // Apply parameter overrides
        if (polish.paramOverrides && operation.parameters) {
          for (const param of operation.parameters) {
            const override = polish.paramOverrides[param.name];
            if (override) {
              if (override.description) param.description = override.description;
              if (override.example !== undefined) param.example = override.example;
            }
          }
        }

        // Apply request body example
        if (polish.requestExample && operation.requestBody?.content?.['application/json']) {
          operation.requestBody.content['application/json'].example = polish.requestExample;
        }
      }

      filteredMethods[method] = operation;
    }

    if (Object.keys(filteredMethods).length > 0) {
      filteredPaths[pathStr] = filteredMethods;
    }
  }

  console.log(`REST API: ${Object.keys(filteredPaths).length} paths`);
  return filteredPaths;
}

// === SANDBOX API PROCESSING ===

function processSandboxApi(spec) {
  console.log('\n=== Processing Sandbox API ===\n');

  const paths = {};

  for (const [pathStr, methods] of Object.entries(spec.paths || {})) {
    // Skip excluded paths
    if (CONFIG.sandboxApi.excludePaths.includes(pathStr)) continue;

    // Add per-path server override
    const processedPath = { servers: [SANDBOX_SERVER] };

    for (const [method, operation] of Object.entries(methods)) {
      if (!operation || typeof operation !== 'object') continue;

      // Apply sandbox endpoint polish
      const polishKey = `${method.toUpperCase()} ${pathStr}`;
      const polish = SANDBOX_ENDPOINT_POLISH[polishKey];
      if (polish) {
        if (polish.summary) operation.summary = polish.summary;
        if (polish.description) operation.description = polish.description;
        if (polish.operationId) operation.operationId = polish.operationId;
        if (polish.tags) operation.tags = polish.tags;
      }

      // Rename tags
      if (operation.tags) {
        operation.tags = operation.tags.map(
          tag => CONFIG.sandboxApi.tagRenames[tag] || tag
        );
      }

      // Ensure AccessTokenAuth security
      operation.security = [{ AccessTokenAuth: [] }];

      processedPath[method] = operation;
    }

    paths[pathStr] = processedPath;
  }

  console.log(`Sandbox API: ${Object.keys(paths).length} paths`);
  return paths;
}

// === COMPONENT PROCESSING ===

function buildComponents(restSpec, sandboxSpec) {
  const components = {
    securitySchemes: {
      ApiKeyAuth: {
        type: 'apiKey',
        in: 'header',
        name: 'X-API-Key',
      },
      AccessTokenAuth: {
        type: 'apiKey',
        in: 'header',
        name: 'X-Access-Token',
      },
    },
    parameters: {},
    responses: {},
    schemas: {},
  };

  // Process REST API parameters with polish (excluding admin-only params)
  if (restSpec.components?.parameters) {
    for (const [name, param] of Object.entries(restSpec.components.parameters)) {
      if (CONFIG.restApi.excludeParameters.has(name)) continue;
      const polished = { ...param };
      if (PARAM_POLISH[name]) {
        if (PARAM_POLISH[name].description) polished.description = PARAM_POLISH[name].description;
        if (PARAM_POLISH[name].example !== undefined) polished.example = PARAM_POLISH[name].example;
      }
      components.parameters[name] = polished;
    }
  }

  // Add sandbox parameters (with Sandbox prefix to avoid collisions)
  if (sandboxSpec.components?.parameters) {
    for (const [name, param] of Object.entries(sandboxSpec.components.parameters)) {
      components.parameters[`Sandbox${name}`] = param;
    }
  }

  // Build polished error responses
  for (const [code, description] of Object.entries(RESPONSE_DESCRIPTIONS)) {
    components.responses[code] = {
      description,
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/Error' },
          ...(RESPONSE_EXAMPLES[code] ? { example: RESPONSE_EXAMPLES[code] } : {}),
        },
      },
    };
  }

  // Process REST API schemas
  if (restSpec.components?.schemas) {
    for (const [name, schema] of Object.entries(restSpec.components.schemas)) {
      // Skip excluded (admin-only) schemas
      if (CONFIG.restApi.excludeSchemas.includes(name)) continue;
      // Skip simple type alias schemas that we inline
      if (INLINE_REFS[name]) continue;

      const polished = polishSchema(name, JSON.parse(JSON.stringify(schema)));
      components.schemas[name] = polished;
    }
  }

  return components;
}

function polishSchema(name, schema) {
  const polish = SCHEMA_POLISH[name];

  // Add top-level description
  if (polish?.description) {
    schema.description = polish.description;
  }

  // Set type to object if not set
  if (!schema.type && schema.properties) {
    schema.type = 'object';
  }

  // Resolve simple $ref properties inline
  if (schema.properties) {
    for (const [propName, prop] of Object.entries(schema.properties)) {
      // Resolve $ref to inline types
      if (prop.$ref) {
        const refName = prop.$ref.replace('#/components/schemas/', '');
        if (INLINE_REFS[refName]) {
          schema.properties[propName] = { ...INLINE_REFS[refName] };
        }
      }

      // Resolve allOf with single $ref (e.g., createdBy)
      if (prop.allOf && prop.allOf.length === 1 && prop.allOf[0].$ref) {
        const refName = prop.allOf[0].$ref.replace('#/components/schemas/', '');
        if (INLINE_REFS[refName]) {
          const { allOf, ...rest } = prop;
          schema.properties[propName] = { ...INLINE_REFS[refName], ...rest };
        }
      }

      // Apply property-level polish
      if (polish?.properties?.[propName]) {
        const propPolish = polish.properties[propName];
        if (propPolish.description) schema.properties[propName].description = propPolish.description;
        if (propPolish.example !== undefined) schema.properties[propName].example = propPolish.example;
      }
    }
  }

  return schema;
}

// === POST-PROCESSING ===

/**
 * Recursively resolve $ref pointers to INLINE_REFS schemas throughout the spec.
 * Also unwraps allOf with a single $ref when pointing to an inline schema.
 */
function resolveInlineRefs(obj) {
  if (!obj || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(item => resolveInlineRefs(item));

  // Handle direct $ref to inline schema
  if (obj.$ref && typeof obj.$ref === 'string') {
    const refName = obj.$ref.replace('#/components/schemas/', '');
    if (INLINE_REFS[refName]) {
      return { ...INLINE_REFS[refName] };
    }
  }

  // Handle allOf with single $ref to inline schema
  if (obj.allOf && obj.allOf.length === 1 && obj.allOf[0].$ref) {
    const refName = obj.allOf[0].$ref.replace('#/components/schemas/', '');
    if (INLINE_REFS[refName]) {
      const { allOf, ...rest } = obj;
      return { ...INLINE_REFS[refName], ...rest };
    }
  }

  // Unwrap allOf with a single $ref (no inline schema, just simplify)
  if (obj.allOf && obj.allOf.length === 1 && Object.keys(obj).length === 1) {
    return resolveInlineRefs(obj.allOf[0]);
  }

  const result = {};
  for (const [key, value] of Object.entries(obj)) {
    result[key] = resolveInlineRefs(value);
  }
  return result;
}

// === UPDATE $REF REFERENCES ===

function updateSandboxRefs(obj, sandboxParamNames) {
  if (!obj || typeof obj !== 'object') return;

  if (obj.$ref && typeof obj.$ref === 'string') {
    // Update parameter references to use Sandbox prefix
    const paramMatch = obj.$ref.match(/^#\/components\/parameters\/(.+)$/);
    if (paramMatch && sandboxParamNames.has(paramMatch[1])) {
      obj.$ref = `#/components/parameters/Sandbox${paramMatch[1]}`;
    }
  }

  for (const value of Object.values(obj)) {
    if (typeof value === 'object' && value !== null) {
      updateSandboxRefs(value, sandboxParamNames);
    }
  }
}

// === MERGE ===

function mergeSpecs(restPaths, sandboxPaths, components) {
  console.log('\n=== Merging Specs ===\n');

  const output = {
    openapi: '3.0.0',
    info: INFO,
    servers: [{ url: 'https://api.e2b.app', description: 'E2B Control Plane API' }],
    tags: TAGS,
    components,
    paths: {},
  };

  // Add REST API paths first (control plane)
  // Organize: sandbox init, then sandboxes, then templates
  const initPath = sandboxPaths['/init'];
  if (initPath) {
    output.paths['/init'] = initPath;
  }

  // Add all REST paths
  for (const [pathStr, methods] of Object.entries(restPaths)) {
    output.paths[pathStr] = methods;
  }

  // Add sandbox paths (data plane) - skip /init which was already added
  for (const [pathStr, methods] of Object.entries(sandboxPaths)) {
    if (pathStr === '/init') continue;
    output.paths[pathStr] = methods;
  }

  const totalPaths = Object.keys(output.paths).length;
  console.log(`Total paths: ${totalPaths}`);

  return output;
}

// === VALIDATION ===

function validateSpec(filename) {
  try {
    const { execSync } = require('child_process');
    execSync(`mintlify openapi-check ${filename}`, { stdio: 'pipe' });
    console.log(`✓ ${filename} is valid`);
    return true;
  } catch (e) {
    if (e.message?.includes('mintlify')) {
      console.log('mintlify CLI not available, skipping validation');
      return true;
    }
    const output = e.stdout?.toString() || e.stderr?.toString() || e.message;
    console.error(`✗ ${filename} validation failed:\n${output}`);
    return false;
  }
}

// === MAIN ===

async function main() {
  console.log('OpenAPI Spec Sync Script');
  console.log('========================\n');
  console.log(`Infra path: ${infraPath}`);

  // Verify source files exist
  if (!fs.existsSync(CONFIG.restApi.source)) {
    console.error(`REST API spec not found: ${CONFIG.restApi.source}`);
    console.error('Clone the infra repo or use --infra-path to specify its location.');
    process.exit(1);
  }
  if (!fs.existsSync(CONFIG.sandboxApi.source)) {
    console.error(`Sandbox API spec not found: ${CONFIG.sandboxApi.source}`);
    process.exit(1);
  }

  try {
    // Load source specs
    const restSpec = loadYaml(CONFIG.restApi.source);
    const sandboxSpec = loadYaml(CONFIG.sandboxApi.source);

    // Process each spec
    const restPaths = processRestApi(restSpec);
    const sandboxPaths = processSandboxApi(sandboxSpec);

    // Build components
    const components = buildComponents(restSpec, sandboxSpec);

    // Track sandbox parameter names for ref updates
    const sandboxParamNames = new Set(
      Object.keys(sandboxSpec.components?.parameters || {})
    );

    // Update $ref references in sandbox paths
    for (const methods of Object.values(sandboxPaths)) {
      updateSandboxRefs(methods, sandboxParamNames);
    }

    // Merge into final spec
    let merged = mergeSpecs(restPaths, sandboxPaths, components);

    // Post-process: resolve inline refs and unwrap unnecessary allOf throughout
    merged = resolveInlineRefs(merged);

    // Reorder operation keys for conventional YAML output
    reorderOperationKeys(merged);

    // Save
    saveYaml(CONFIG.output, merged);

    // Validate
    console.log('\n=== Validation ===\n');
    validateSpec(CONFIG.output);

    console.log('\n✓ Done!\n');
  } catch (error) {
    console.error(`\n✗ Error: ${error.message}\n`);
    console.error(error.stack);
    process.exit(1);
  }
}

main();
