# SDK Reference Documentation Generator

TypeScript-based documentation generator for E2B SDKs with automatic versioning, caching, and CI/CD integration.

## Features

- **Multi-SDK Support**: JS, Python, CLI, Code Interpreter, Desktop SDKs
- **Automatic Version Discovery**: Detects and generates missing versions
- **Intelligent Caching**: Skips reinstalling dependencies when lockfile unchanged
- **Idempotent**: Safe to run repeatedly, only generates what's missing
- **Full Visibility**: Complete logging of all subcommands for debugging
- **Verification**: Validates generated docs before finalizing
- **CI/CD Ready**: GitHub Actions integration with safety checks

## Usage

```bash
# generate all SDKs, all versions
pnpm run generate

# generate specific SDK, latest version
pnpm run generate --sdk js-sdk --version latest

# generate specific version
pnpm run generate --sdk python-sdk --version v2.8.0

# limit to last N versions (useful for testing)
pnpm run generate --sdk all --version all --limit 5

# force regenerate existing versions (useful after config changes)
pnpm run generate --sdk js-sdk --version all --force

# combine flags
pnpm run generate --sdk all --version all --limit 3 --force
```

## Architecture

```
src/
├── cli.ts              # Entry point with CLI argument parsing
├── generator.ts        # Core SDK generation orchestration
├── navigation.ts       # Mintlify navigation builder
├── types.ts            # TypeScript interfaces
├── lib/
│   ├── constants.ts    # Centralized magic strings
│   ├── utils.ts        # Pure utility functions
│   ├── git.ts          # Git operations (clone, tags)
│   ├── checkout.ts     # Manages repo checkouts and version switching
│   ├── versions.ts     # Version comparison and filtering
│   ├── files.ts        # Markdown processing and flattening
│   ├── install.ts      # Package manager abstraction
│   └── verify.ts       # Post-generation validation
└── generators/
    ├── typedoc.ts      # JavaScript/TypeScript docs
    ├── pydoc.ts        # Python docs
    └── cli.ts          # CLI command docs
```

## Configuration

SDKs are configured in `sdks.json`:

```json
{
  "sdks": {
    "js-sdk": {
      "displayName": "SDK (JavaScript)",
      "icon": "square-js",
      "order": 1,
      "repo": "https://github.com/e2b-dev/e2b.git",
      "tagPattern": "e2b@",
      "tagFormat": "e2b@{version}",
      "generator": "typedoc",
      "required": true,
      "minVersion": "1.0.0",
      "sdkPath": "packages/js-sdk"
    }
  }
}
```

## Error Handling

### Strict Safety Model

1. **Required SDKs**: Any failure aborts workflow
2. **Optional SDKs**: All versions failing aborts workflow
3. **Partial failures**: Non-required SDK with some successes continues
4. **Verification**: Post-generation validation ensures quality

### Progressive Dependency Resolution

For maximum compatibility across SDK versions:

1. **Try pnpm install** - Primary package manager with caching
2. **Try npm fallback** - Uses npm with `--force` and `--legacy-peer-deps`

Each strategy visible in logs for debugging. If both strategies fail, workflow aborts.

### What Gets Logged

- ✅ Package manager output (pnpm/npm/poetry/pip)
- ✅ Build tool output (TypeDoc, pydoc-markdown, CLI builds)
- ✅ File operations (copying, flattening)
- ✅ Validation results (empty files, missing frontmatter)
- ✅ Final statistics (files, SDKs, versions)

## Verification Checks

Before finalizing, the generator verifies:

1. **Generated Files**: No empty MDX files
2. **Frontmatter**: All files have proper frontmatter
3. **Structure**: Valid directory structure
4. **docs.json**: Valid JSON with correct navigation structure

## Testing

```bash
# run unit tests
pnpm test

# run with watch mode
pnpm test:watch

# type check
npx tsc --noEmit
```

Tests cover:
- Version comparison and filtering (10 tests)
- File operations and title casing (5 tests)
- Verification logic (7 tests)

## CI/CD Integration

The generator runs in GitHub Actions on:
- Manual workflow dispatch
- Automatic repository dispatch from SDK repos on release
- Scheduled sync every 15 minutes

### Manual Trigger (GitHub UI)

1. Go to **Actions** → **Sync SDK Reference Documentation**
2. Click **Run workflow**
3. Fill in:
   - **SDK**: `all`, or specific SDK key (e.g., `js-sdk`, `python-sdk`, `cli`)
   - **Version**: `all`, `latest`, or specific version (e.g., `v2.9.0`)

### Manual Trigger (GitHub CLI)

```bash
# generate all SDKs, all versions
gh workflow run sdk-reference-sync.yml -f sdk=all -f version=all

# generate specific SDK, latest version
gh workflow run sdk-reference-sync.yml -f sdk=js-sdk -f version=latest

# generate specific version
gh workflow run sdk-reference-sync.yml -f sdk=python-sdk -f version=v2.8.0
```

### Repository Dispatch (from SDK repos)

SDK repositories can trigger doc generation on release:

```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/e2b-dev/docs/dispatches \
  -d '{"event_type": "sdk-release", "client_payload": {"sdk": "js-sdk", "version": "v2.9.0"}}'
```

### Scheduled Sync

The sync workflow also runs on a 15-minute cron interval:

```text
*/15 * * * *
```

Scheduled runs default to:
- **SDK**: `all`
- **Version**: `all`
- **Limit**: `3`
- **Force**: `false`

This acts as a polling safety net if an SDK release event is missed, while keeping the scheduled scan bounded to the latest three versions per SDK.

### Output Behavior

The sync workflow no longer pushes directly to `main`.

When generated docs change, the workflow now:
- Creates or updates an automation branch
- Opens a structured pull request with trigger metadata, generation parameters, and a link to the workflow run
- Limits committed paths to `docs/sdk-reference/**` and `docs.json`

### Safety Features

- Validates all generated files before committing
- Only creates a pull request if changes are detected
- Full logging visible in workflow runs
- User inputs passed via environment variables (prevents script injection)

## Performance

- **Checkout Reuse**: Repository cloned once, versions switched via git checkout
- **Version Deduplication**: Batch comparison skips already-generated versions
- **Parallel Generation**: Could process multiple versions concurrently (future enhancement)

## Development

```bash
# install dependencies
pnpm install

# run generator locally
pnpm run generate --sdk js-sdk --limit 1

# run tests
pnpm test
```
