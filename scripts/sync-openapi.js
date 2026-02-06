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

const CONFIG = {
  output: 'openapi-public.yml',

  // REST API configuration
  restApi: {
    source: `${INFRA_RAW_BASE}/spec/openapi.yml`,
    excludePaths: [
      '/access-tokens',
      '/access-tokens/{accessTokenID}',
      '/admin/teams/{teamID}/sandboxes/kill',
      '/api-keys',
      '/api-keys/{apiKeyID}',
      '/health',
      '/nodes',
      '/nodes/{nodeID}',
      '/teams',
    ],
    removeSecuritySchemes: [
      'Supabase1TokenAuth',
      'Supabase2TeamAuth',
      'AccessTokenAuth',
      'AdminTokenAuth',
    ],
  },

  // Sandbox API configuration
  sandboxApi: {
    envdSource: `${INFRA_RAW_BASE}/packages/envd/spec/envd.yaml`,
    filesystemProto: `${INFRA_RAW_BASE}/packages/envd/spec/filesystem/filesystem.proto`,
    processProto: `${INFRA_RAW_BASE}/packages/envd/spec/process/process.proto`,
    excludePaths: [
      '/metrics',
      '/envs',
      '/health'
    ],
    removeSchemas: [
      'connect-protocol-version',
      'connect-timeout-header',
      'connect.error'
    ],
    removeHeaders: [
      'Connect-Protocol-Version',
      'Connect-Timeout-Ms'
    ],
    // Tag renames for sandbox endpoints
    tagRenames: {
      'filesystem.Filesystem': 'Sandbox Filesystem',
      'process.Process': 'Sandbox Process',
      'files': 'Sandbox Files'
    }
  },

  info: {
    title: 'E2B API',
    description: `API for managing and interacting with E2B sandboxes.

## REST API (api.e2b.app)
Endpoints for creating and managing sandboxes and templates.
- **Authentication**: \`X-API-Key\` header with your API key from the [E2B Dashboard](https://e2b.dev/dashboard?tab=keys)
- **Base URL**: \`https://api.e2b.app\`

## Sandbox API ({sandboxID}.e2b.app)
Endpoints for interacting with files and processes inside a running sandbox.
- **Authentication**: \`X-Access-Token\` header with the access token received when creating a sandbox
- **Base URL**: \`https://{sandboxID}.e2b.app\`
`
  }
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

// === REST API PROCESSING ===

async function fetchRestApiSpec() {
  console.log('\n=== Fetching REST API Spec ===\n');

  const spec = await fetchYaml(CONFIG.restApi.source);

  // Filter out excluded paths AND endpoints that only use Supabase tokens
  const filteredPaths = {};
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    if (CONFIG.restApi.excludePaths.includes(path)) {
      continue;
    }

    const filteredMethods = {};
    for (const [method, operation] of Object.entries(methods)) {
      if (!operation.security && !operation.responses) {
        filteredMethods[method] = operation;
        continue;
      }

      const hasApiKeyAuth = operation.security?.some(secObj =>
        Object.keys(secObj).includes('ApiKeyAuth')
      );

      if (hasApiKeyAuth || !operation.security) {
        filteredMethods[method] = operation;
      }
    }

    if (Object.keys(filteredMethods).length > 0) {
      filteredPaths[path] = filteredMethods;
    }
  }
  spec.paths = filteredPaths;
  console.log(`REST API: ${Object.keys(filteredPaths).length} endpoints`);

  // Keep only ApiKeyAuth security scheme
  if (spec.components?.securitySchemes?.ApiKeyAuth) {
    spec.components.securitySchemes = {
      ApiKeyAuth: spec.components.securitySchemes.ApiKeyAuth
    };
  }

  // Clean up security references
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation.security) {
        operation.security = operation.security.filter(secObj => {
          const schemes = Object.keys(secObj);
          return schemes.length === 0 || schemes.includes('ApiKeyAuth');
        });
        if (operation.security.length === 0) {
          delete operation.security;
        }
      }
    }
  }

  return spec;
}

// === SANDBOX API PROCESSING ===

async function fetchSandboxApiSpec() {
  console.log('\n=== Fetching Sandbox API Spec ===\n');

  const spec = await fetchYaml(CONFIG.sandboxApi.envdSource);

  // Fix security scheme
  if (spec.components?.securitySchemes?.AccessTokenAuth) {
    spec.components.securitySchemes.AccessTokenAuth = {
      type: 'apiKey',
      in: 'header',
      name: 'X-Access-Token',
      description: 'Access token received when creating a sandbox'
    };
  }

  // Try to merge proto-based specs
  try {
    await mergeProtoSpecs(spec);
  } catch (e) {
    console.warn(`Warning: Could not generate proto specs: ${e.message}`);
  }

  // Filter out internal endpoints
  for (const excludePath of CONFIG.sandboxApi.excludePaths) {
    if (spec.paths[excludePath]) {
      delete spec.paths[excludePath];
      console.log(`Excluded: ${excludePath}`);
    }
  }

  // Rename tags to include "Sandbox" prefix
  for (const [path, methods] of Object.entries(spec.paths || {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation.tags) {
        operation.tags = operation.tags.map(tag =>
          CONFIG.sandboxApi.tagRenames[tag] || `Sandbox ${tag}`
        );
      } else {
        // Add default tag for untagged endpoints
        operation.tags = ['Sandbox'];
      }
    }
  }

  // Apply schema fixes
  applySchemaFixes(spec);

  console.log(`Sandbox API: ${Object.keys(spec.paths || {}).length} endpoints`);
  return spec;
}

async function mergeProtoSpecs(spec) {
  try {
    execSync('which buf', { stdio: 'pipe' });
    execSync('which protoc-gen-connect-openapi', { stdio: 'pipe' });
  } catch (e) {
    throw new Error('buf or protoc-gen-connect-openapi not installed');
  }

  const tempDir = fs.mkdtempSync(path.join(require('os').tmpdir(), 'openapi-'));
  console.log(`Using temp directory: ${tempDir}`);

  try {
    const filesystemProto = await fetchText(CONFIG.sandboxApi.filesystemProto);
    const processProto = await fetchText(CONFIG.sandboxApi.processProto);

    fs.mkdirSync(path.join(tempDir, 'filesystem'), { recursive: true });
    fs.mkdirSync(path.join(tempDir, 'process'), { recursive: true });
    fs.writeFileSync(path.join(tempDir, 'filesystem', 'filesystem.proto'), filesystemProto);
    fs.writeFileSync(path.join(tempDir, 'process', 'process.proto'), processProto);

    fs.writeFileSync(path.join(tempDir, 'buf.yaml'), 'version: v1\n');

    const bufGenYaml = `version: v2
plugins:
  - local: protoc-gen-connect-openapi
    out: .
    opt:
      - with-streaming
`;
    fs.writeFileSync(path.join(tempDir, 'buf.gen.yaml'), bufGenYaml);

    console.log('Running buf generate...');
    execSync('buf generate', { cwd: tempDir, stdio: 'pipe' });

    const filesystemSpecPath = path.join(tempDir, 'filesystem', 'filesystem.openapi.yaml');
    const processSpecPath = path.join(tempDir, 'process', 'process.openapi.yaml');

    if (fs.existsSync(filesystemSpecPath)) {
      const filesystemSpec = yaml.load(fs.readFileSync(filesystemSpecPath, 'utf8'));
      mergeSpecPaths(spec, filesystemSpec, '/filesystem.');
    }

    if (fs.existsSync(processSpecPath)) {
      const processSpec = yaml.load(fs.readFileSync(processSpecPath, 'utf8'));
      mergeSpecPaths(spec, processSpec, '/process.');
    }

    console.log('Merged filesystem and process endpoints');

  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function mergeSpecPaths(target, source, pathPrefix) {
  for (const [path, methods] of Object.entries(source.paths || {})) {
    if (path.startsWith(pathPrefix)) {
      target.paths[path] = methods;
    }
  }

  if (source.components?.schemas) {
    target.components = target.components || {};
    target.components.schemas = target.components.schemas || {};
    Object.assign(target.components.schemas, source.components.schemas);
  }
}

function applySchemaFixes(spec) {
  if (spec.components?.schemas) {
    for (const schemaName of CONFIG.sandboxApi.removeSchemas) {
      if (spec.components.schemas[schemaName]) {
        delete spec.components.schemas[schemaName];
      }
    }
    fixInvalidTypeArrays(spec.components.schemas);
  }

  for (const [path, methods] of Object.entries(spec.paths || {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation.parameters) {
        operation.parameters = operation.parameters.filter(p =>
          !CONFIG.sandboxApi.removeHeaders.includes(p.name)
        );
      }

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

function fixInvalidTypeArrays(schemas) {
  for (const [name, schema] of Object.entries(schemas)) {
    fixTypeArraysRecursive(schema);
  }
}

function fixTypeArraysRecursive(obj) {
  if (!obj || typeof obj !== 'object') return;

  if (Array.isArray(obj.type)) {
    const mainType = obj.type.find(t => t !== 'null') || obj.type[0];
    obj.type = mainType;
  }

  if (obj.examples && !obj.example) {
    obj.example = Array.isArray(obj.examples) ? obj.examples[0] : obj.examples;
    delete obj.examples;
  }

  if (Array.isArray(obj.oneOf)) {
    const nullIndex = obj.oneOf.findIndex(item => item.type === 'null');
    if (nullIndex !== -1) {
      obj.oneOf.splice(nullIndex, 1);
      obj.nullable = true;
      if (obj.oneOf.length === 1) {
        const remaining = obj.oneOf[0];
        delete obj.oneOf;
        Object.assign(obj, remaining);
      } else if (obj.oneOf.length === 0) {
        delete obj.oneOf;
      }
    }
  }

  if (obj.properties) {
    for (const prop of Object.values(obj.properties)) {
      fixTypeArraysRecursive(prop);
    }
  }

  if (obj.items) {
    fixTypeArraysRecursive(obj.items);
  }

  if (obj.additionalProperties && typeof obj.additionalProperties === 'object') {
    fixTypeArraysRecursive(obj.additionalProperties);
  }

  for (const key of ['allOf', 'oneOf', 'anyOf']) {
    if (Array.isArray(obj[key])) {
      for (const item of obj[key]) {
        fixTypeArraysRecursive(item);
      }
    }
  }
}

// === MERGE SPECS ===

function mergeSpecs(restSpec, sandboxSpec) {
  console.log('\n=== Merging Specs ===\n');

  // Start with REST API spec as base
  const merged = restSpec;

  // Update info
  merged.info.title = CONFIG.info.title;
  merged.info.description = CONFIG.info.description;

  // Add AccessTokenAuth security scheme for sandbox endpoints
  merged.components.securitySchemes.AccessTokenAuth = {
    type: 'apiKey',
    in: 'header',
    name: 'X-Access-Token',
    description: 'Access token received when creating a sandbox (for Sandbox API endpoints)'
  };

  // Track sandbox paths for ref updates
  const sandboxPaths = new Set(Object.keys(sandboxSpec.paths || {}));

  // Sandbox API server (different host)
  const sandboxServer = {
    url: 'https://{port}-{sandboxId}.e2b.app',
    description: 'Sandbox API',
    variables: {
      port: {
        default: '49982',
        description: 'Port number for the sandbox API'
      },
      sandboxId: {
        default: 'sandbox-id',
        description: 'Sandbox ID returned when creating a sandbox'
      }
    }
  };

  // Merge sandbox paths with per-path server override
  for (const [path, methods] of Object.entries(sandboxSpec.paths || {})) {
    // Add server override for this path
    merged.paths[path] = {
      servers: [sandboxServer],
      ...methods
    };

    // Update security to use AccessTokenAuth for sandbox endpoints
    for (const [method, operation] of Object.entries(methods)) {
      if (typeof operation === 'object' && operation !== null && !Array.isArray(operation)) {
        operation.security = [{ AccessTokenAuth: [] }];
      }
    }
  }

  // Merge sandbox components (schemas, requestBodies, responses, parameters)
  const componentTypes = ['schemas', 'requestBodies', 'responses', 'parameters'];
  for (const componentType of componentTypes) {
    if (sandboxSpec.components?.[componentType]) {
      merged.components[componentType] = merged.components[componentType] || {};
      for (const [name, component] of Object.entries(sandboxSpec.components[componentType])) {
        const prefixedName = `Sandbox${name}`;
        merged.components[componentType][prefixedName] = component;
      }
    }
  }

  // Update $ref references in sandbox paths and components
  for (const [path, methods] of Object.entries(merged.paths)) {
    if (sandboxPaths.has(path)) {
      updateSchemaRefs(methods, 'Sandbox');
    }
  }
  // Also update refs within sandbox components themselves
  for (const componentType of componentTypes) {
    for (const [name, component] of Object.entries(merged.components[componentType] || {})) {
      if (name.startsWith('Sandbox')) {
        updateSchemaRefs(component, 'Sandbox');
      }
    }
  }

  // Add tags
  merged.tags = [
    ...(merged.tags || []),
    { name: 'Sandbox', description: 'Sandbox initialization' },
    { name: 'Sandbox Files', description: 'Upload and download files in sandbox' },
    { name: 'Sandbox Filesystem', description: 'Filesystem operations (list, create, move, delete)' },
    { name: 'Sandbox Process', description: 'Process management (start, stop, send input)' }
  ];

  const totalEndpoints = Object.keys(merged.paths).length;
  console.log(`Total endpoints: ${totalEndpoints}`);

  return merged;
}

function updateSchemaRefs(obj, prefix) {
  if (!obj || typeof obj !== 'object') return;

  // Handle all component $ref types
  if (obj.$ref && obj.$ref.startsWith('#/components/')) {
    const match = obj.$ref.match(/^#\/components\/(\w+)\/(.+)$/);
    if (match) {
      const [, componentType, name] = match;
      // Don't prefix common schemas that exist in REST API
      if (!['Error'].includes(name)) {
        obj.$ref = `#/components/${componentType}/${prefix}${name}`;
      }
    }
  }

  for (const value of Object.values(obj)) {
    if (typeof value === 'object') {
      updateSchemaRefs(value, prefix);
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
    // Fetch both specs
    const restSpec = await fetchRestApiSpec();
    const sandboxSpec = await fetchSandboxApiSpec();

    // Merge into single spec
    const merged = mergeSpecs(restSpec, sandboxSpec);

    // Save merged spec
    saveYaml(CONFIG.output, merged);

    // Remove old sandbox spec if exists
    const oldSandboxSpec = 'openapi-sandbox.yml';
    if (fs.existsSync(oldSandboxSpec)) {
      fs.unlinkSync(oldSandboxSpec);
      console.log(`Removed old: ${oldSandboxSpec}`);
    }

    console.log('\n=== Validation ===\n');

    try {
      execSync('which mintlify', { stdio: 'pipe' });
      validateSpec(CONFIG.output);
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
