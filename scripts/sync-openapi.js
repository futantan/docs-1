#!/usr/bin/env node

/**
 * OpenAPI Spec Sync Script
 *
 * Fetches OpenAPI specs from e2b-dev/infra repository, transforms them
 * for public documentation, and saves them to the docs repo.
 *
 * Usage: node scripts/sync-openapi.js
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Try to load js-yaml, install if not available
let yaml;
try {
  yaml = require('js-yaml');
} catch (e) {
  console.log('Installing js-yaml...');
  execSync('npm install js-yaml', { stdio: 'inherit' });
  yaml = require('js-yaml');
}

const INFRA_RAW_BASE = 'https://raw.githubusercontent.com/e2b-dev/infra/main';

// === CONFIGURATION ===

const REST_API_CONFIG = {
  source: `${INFRA_RAW_BASE}/spec/openapi.yml`,
  output: 'openapi-public.yml',
  excludePaths: [
    '/access-tokens',
    '/access-tokens/{accessTokenID}',
    '/admin/teams/{teamID}/sandboxes/kill',
    '/api-keys',
    '/api-keys/{apiKeyID}',
    '/nodes',
    '/nodes/{nodeID}',
    '/teams',
  ],
  // Security schemes to remove from endpoints (keep only ApiKeyAuth)
  removeSecuritySchemes: [
    'Supabase1TokenAuth',
    'Supabase2TeamAuth',
    'AccessTokenAuth',
    'AdminTokenAuth',
  ],
  info: {
    title: 'E2B REST API',
    description: `REST API for managing E2B sandboxes and templates.

## Authentication
All endpoints require authentication via API key passed in the \`X-API-Key\` header.
Get your API key from the [E2B Dashboard](https://e2b.dev/dashboard?tab=keys).

## Base URL
\`\`\`
https://api.e2b.app
\`\`\`
`
  }
};

const SANDBOX_API_CONFIG = {
  envdSource: `${INFRA_RAW_BASE}/packages/envd/spec/envd.yaml`,
  filesystemProto: `${INFRA_RAW_BASE}/packages/envd/spec/filesystem/filesystem.proto`,
  processProto: `${INFRA_RAW_BASE}/packages/envd/spec/process/process.proto`,
  output: 'openapi-sandbox.yml',
  info: {
    title: 'E2B Sandbox API',
    description: `API for interacting with files and processes inside E2B sandboxes.

## Authentication
All endpoints require the \`X-Access-Token\` header with the access token received when creating a sandbox.

## Base URL
\`\`\`
https://{sandboxID}.e2b.app
\`\`\`

## Getting the Access Token
1. Create a sandbox via REST API: \`POST https://api.e2b.app/sandboxes\`
2. Response includes \`sandboxID\` and \`envdAccessToken\`
3. Use \`envdAccessToken\` as \`X-Access-Token\` header for all Sandbox API calls
`
  },
  // Connect RPC schemas to remove (protocol-level, not user-facing)
  removeSchemas: [
    'connect-protocol-version',
    'connect-timeout-header',
    'connect.error'
  ],
  // Connect headers to remove from endpoint parameters
  removeHeaders: [
    'Connect-Protocol-Version',
    'Connect-Timeout-Ms'
  ]
};

// === UTILITY FUNCTIONS ===

async function fetchYaml(url) {
  console.log(`Fetching: ${url}`);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  const text = await response.text();
  return yaml.load(text);
}

async function fetchText(url) {
  console.log(`Fetching: ${url}`);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  return response.text();
}

function saveYaml(filename, data) {
  const outputPath = path.join(process.cwd(), filename);
  fs.writeFileSync(outputPath, yaml.dump(data, { lineWidth: -1, noRefs: true }));
  console.log(`Saved: ${outputPath}`);
}

// === REST API SPEC GENERATION ===

async function generateRestApiSpec() {
  console.log('\n=== Generating REST API Spec ===\n');

  const spec = await fetchYaml(REST_API_CONFIG.source);

  // Filter out excluded paths AND endpoints that only use Supabase tokens
  const filteredPaths = {};
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    // Skip explicitly excluded paths
    if (REST_API_CONFIG.excludePaths.includes(path)) {
      continue;
    }

    // Check each method in this path
    const filteredMethods = {};
    for (const [method, operation] of Object.entries(methods)) {
      // Skip non-operation properties like 'parameters'
      if (!operation.security && !operation.responses) {
        filteredMethods[method] = operation;
        continue;
      }

      // Check if this endpoint has ApiKeyAuth
      const hasApiKeyAuth = operation.security?.some(secObj =>
        Object.keys(secObj).includes('ApiKeyAuth')
      );

      // Keep endpoint only if it has ApiKeyAuth (or no security = public)
      if (hasApiKeyAuth || !operation.security) {
        filteredMethods[method] = operation;
      }
    }

    // Only add path if it has any methods left
    if (Object.keys(filteredMethods).length > 0) {
      filteredPaths[path] = filteredMethods;
    }
  }
  spec.paths = filteredPaths;
  console.log(`Filtered paths: ${Object.keys(filteredPaths).length} remaining`);

  // Keep only ApiKeyAuth security scheme
  if (spec.components?.securitySchemes?.ApiKeyAuth) {
    spec.components.securitySchemes = {
      ApiKeyAuth: spec.components.securitySchemes.ApiKeyAuth
    };
  }

  // Clean up security references in endpoints - remove Supabase/AccessToken refs
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation.security) {
        // Filter out security schemes we don't want
        operation.security = operation.security.filter(secObj => {
          const schemes = Object.keys(secObj);
          // Keep only if it has ApiKeyAuth or is empty (public endpoint)
          return schemes.length === 0 || schemes.includes('ApiKeyAuth');
        });
        // If no security left, remove the property (makes it use global security)
        if (operation.security.length === 0) {
          delete operation.security;
        }
      }
    }
  }

  // Update info section
  spec.info.title = REST_API_CONFIG.info.title;
  spec.info.description = REST_API_CONFIG.info.description;

  saveYaml(REST_API_CONFIG.output, spec);
  return spec;
}

// === SANDBOX API SPEC GENERATION ===

async function generateSandboxApiSpec() {
  console.log('\n=== Generating Sandbox API Spec ===\n');

  // Fetch base envd.yaml
  const spec = await fetchYaml(SANDBOX_API_CONFIG.envdSource);

  // Fix security scheme (scheme: header -> in: header)
  if (spec.components?.securitySchemes?.AccessTokenAuth) {
    spec.components.securitySchemes.AccessTokenAuth = {
      type: 'apiKey',
      in: 'header',
      name: 'X-Access-Token',
      description: 'Access token received when creating a sandbox'
    };
  }

  // Update info section
  spec.info.title = SANDBOX_API_CONFIG.info.title;
  spec.info.description = SANDBOX_API_CONFIG.info.description;

  // Try to generate and merge proto-based specs
  try {
    await mergeProtoSpecs(spec);
  } catch (e) {
    console.warn(`Warning: Could not generate proto specs: ${e.message}`);
    console.warn('Sandbox API will only include REST endpoints (/files, /health, etc.)');
  }

  // Apply fixes
  applySchemaFixes(spec);

  saveYaml(SANDBOX_API_CONFIG.output, spec);
  return spec;
}

async function mergeProtoSpecs(spec) {
  // Check if buf and protoc-gen-connect-openapi are available
  try {
    execSync('which buf', { stdio: 'pipe' });
    execSync('which protoc-gen-connect-openapi', { stdio: 'pipe' });
  } catch (e) {
    throw new Error('buf or protoc-gen-connect-openapi not installed');
  }

  // Create temp directory for proto generation
  const tempDir = fs.mkdtempSync(path.join(require('os').tmpdir(), 'openapi-'));
  console.log(`Using temp directory: ${tempDir}`);

  try {
    // Fetch proto files
    const filesystemProto = await fetchText(SANDBOX_API_CONFIG.filesystemProto);
    const processProto = await fetchText(SANDBOX_API_CONFIG.processProto);

    // Write proto files
    fs.mkdirSync(path.join(tempDir, 'filesystem'), { recursive: true });
    fs.mkdirSync(path.join(tempDir, 'process'), { recursive: true });
    fs.writeFileSync(path.join(tempDir, 'filesystem', 'filesystem.proto'), filesystemProto);
    fs.writeFileSync(path.join(tempDir, 'process', 'process.proto'), processProto);

    // Write buf.yaml
    fs.writeFileSync(path.join(tempDir, 'buf.yaml'), 'version: v1\n');

    // Write buf.gen.yaml for OpenAPI generation
    const bufGenYaml = `version: v2
plugins:
  - local: protoc-gen-connect-openapi
    out: .
    opt:
      - with-streaming
`;
    fs.writeFileSync(path.join(tempDir, 'buf.gen.yaml'), bufGenYaml);

    // Run buf generate
    console.log('Running buf generate...');
    execSync('buf generate', { cwd: tempDir, stdio: 'pipe' });

    // Load generated specs
    const filesystemSpecPath = path.join(tempDir, 'filesystem', 'filesystem.openapi.yaml');
    const processSpecPath = path.join(tempDir, 'process', 'process.openapi.yaml');

    if (fs.existsSync(filesystemSpecPath)) {
      const filesystemSpec = yaml.load(fs.readFileSync(filesystemSpecPath, 'utf8'));
      mergeSpec(spec, filesystemSpec, '/filesystem.');
    }

    if (fs.existsSync(processSpecPath)) {
      const processSpec = yaml.load(fs.readFileSync(processSpecPath, 'utf8'));
      mergeSpec(spec, processSpec, '/process.');
    }

    console.log('Merged filesystem and process endpoints');

  } finally {
    // Cleanup temp directory
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function fixInvalidTypeArrays(schemas) {
  // Recursively fix type arrays in schemas (OpenAPI 3.0 doesn't support type arrays)
  for (const [name, schema] of Object.entries(schemas)) {
    fixTypeArraysRecursive(schema);
  }
}

function fixTypeArraysRecursive(obj) {
  if (!obj || typeof obj !== 'object') return;

  // Fix type arrays - convert to first type (usually the main type)
  if (Array.isArray(obj.type)) {
    // Use the first non-null type
    const mainType = obj.type.find(t => t !== 'null') || obj.type[0];
    obj.type = mainType;
  }

  // Fix examples -> example (OpenAPI 3.0 uses singular for schemas)
  if (obj.examples && !obj.example) {
    obj.example = Array.isArray(obj.examples) ? obj.examples[0] : obj.examples;
    delete obj.examples;
  }

  // Fix oneOf with type: 'null' -> nullable: true (OpenAPI 3.0 style)
  if (Array.isArray(obj.oneOf)) {
    const nullIndex = obj.oneOf.findIndex(item => item.type === 'null');
    if (nullIndex !== -1) {
      // Remove the null type from oneOf
      obj.oneOf.splice(nullIndex, 1);
      obj.nullable = true;
      // If only one item left, unwrap the oneOf
      if (obj.oneOf.length === 1) {
        const remaining = obj.oneOf[0];
        delete obj.oneOf;
        Object.assign(obj, remaining);
      } else if (obj.oneOf.length === 0) {
        delete obj.oneOf;
      }
    }
  }

  // Recurse into properties
  if (obj.properties) {
    for (const prop of Object.values(obj.properties)) {
      fixTypeArraysRecursive(prop);
    }
  }

  // Recurse into items (for arrays)
  if (obj.items) {
    fixTypeArraysRecursive(obj.items);
  }

  // Recurse into additionalProperties
  if (obj.additionalProperties && typeof obj.additionalProperties === 'object') {
    fixTypeArraysRecursive(obj.additionalProperties);
  }

  // Recurse into allOf/oneOf/anyOf
  for (const key of ['allOf', 'oneOf', 'anyOf']) {
    if (Array.isArray(obj[key])) {
      for (const item of obj[key]) {
        fixTypeArraysRecursive(item);
      }
    }
  }
}

function mergeSpec(target, source, pathPrefix) {
  // Merge paths
  for (const [path, methods] of Object.entries(source.paths || {})) {
    if (path.startsWith(pathPrefix)) {
      target.paths[path] = methods;
    }
  }

  // Merge schemas
  if (source.components?.schemas) {
    target.components = target.components || {};
    target.components.schemas = target.components.schemas || {};
    Object.assign(target.components.schemas, source.components.schemas);
  }

  // Merge tags
  if (source.tags) {
    target.tags = target.tags || [];
    const existingTags = new Set(target.tags.map(t => t.name));
    for (const tag of source.tags) {
      if (!existingTags.has(tag.name)) {
        target.tags.push(tag);
      }
    }
  }
}

function applySchemaFixes(spec) {
  // Remove Connect protocol schemas
  if (spec.components?.schemas) {
    for (const schemaName of SANDBOX_API_CONFIG.removeSchemas) {
      if (spec.components.schemas[schemaName]) {
        delete spec.components.schemas[schemaName];
        console.log(`Removed schema: ${schemaName}`);
      }
    }

    // Fix invalid type arrays (e.g., type: [integer, string] -> oneOf)
    fixInvalidTypeArrays(spec.components.schemas);
  }

  // Remove Connect headers from endpoint parameters
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation.parameters) {
        const filtered = operation.parameters.filter(p =>
          !SANDBOX_API_CONFIG.removeHeaders.includes(p.name)
        );
        if (filtered.length !== operation.parameters.length) {
          operation.parameters = filtered;
        }
      }

      // Replace connect.error references with standard Error
      if (operation.responses) {
        for (const [code, response] of Object.entries(operation.responses)) {
          if (response.content?.['application/json']?.schema?.$ref === '#/components/schemas/connect.error') {
            response.content['application/json'].schema.$ref = '#/components/schemas/Error';
          }
        }
      }
    }
  }
}

// === VALIDATION ===

function validateSpec(filename) {
  try {
    execSync(`mintlify openapi-check ${filename}`, { stdio: 'pipe' });
    console.log(`✓ ${filename} is valid`);
    return true;
  } catch (e) {
    const output = e.stdout?.toString() || e.stderr?.toString() || e.message;
    console.error(`✗ ${filename} validation failed:\n${output}`);
    return false;
  }
}

// === MAIN ===

async function main() {
  console.log('OpenAPI Spec Sync Script');
  console.log('========================\n');

  try {
    // Generate REST API spec
    await generateRestApiSpec();

    // Generate Sandbox API spec
    await generateSandboxApiSpec();

    console.log('\n=== Validation ===\n');

    // Validate if mintlify is available
    try {
      execSync('which mintlify', { stdio: 'pipe' });
      validateSpec(REST_API_CONFIG.output);
      validateSpec(SANDBOX_API_CONFIG.output);
    } catch (e) {
      console.log('mintlify CLI not available, skipping validation');
    }

    console.log('\n✓ Done!\n');

  } catch (error) {
    console.error(`\n✗ Error: ${error.message}\n`);
    process.exit(1);
  }
}

main();
