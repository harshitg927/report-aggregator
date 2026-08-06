<!-- SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

     SPDX-License-Identifier: MIT
-->

# Report Aggregator

Merge N FOSSology-generated reports into one deduplicated report of the same format.
This repository is a **monorepo** containing both the Python merge/edit engine and the
Next.js web UI.

## Repository Layout

```
report-aggregator/
├── src/report_aggregator/   # Python engine (merge, edit, provenance) + FastAPI service
├── tests/                   # pytest suite
├── frontend/                # Next.js front-end (report-aggregator-ui)
│   ├── app/                 # Next.js App Router pages
│   ├── components/          # React components
│   ├── lib/                 # Shared utilities and API client
│   └── README.md            # Frontend-specific documentation
├── Dockerfile               # Python API + CLI image
├── docker-compose.yml       # Full stack (API + UI)
├── Makefile                 # Convenience targets (install, dev, test, lint, docker)
├── pyproject.toml           # Python package config
└── README.md                # This file
```

## Quick Start (Full Stack)

```bash
# 1. Install Python engine + API extra
pip install -e ".[api,dev]"

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3a. Start both services together
cd frontend && npm run dev:all
# API → http://127.0.0.1:8000
# UI  → http://localhost:3000

# 3b. Or start them in separate terminals
make dev-api   # terminal 1 — FastAPI service
make dev-ui    # terminal 2 — Next.js dev server
```

See [`frontend/README.md`](frontend/README.md) for full frontend documentation.

## Docker

The repo ships one Python image (API by default, CLI via command override) and one
Next.js frontend image. Compose runs the full stack.

```bash
# Full stack — API http://localhost:8000 , UI http://localhost:3000
docker compose up --build
# or: make docker-up

# API only
docker build -t report-aggregator:latest .
docker run --rm -p 8000:8000 -v ra-workspaces:/data/workspaces report-aggregator:latest

# CLI merge (mount your working directory)
docker run --rm -v "$PWD:/work" -w /work report-aggregator:latest \
  report-aggregator merge report-a.json report-b.json -o merged.json
```

Stop the stack with `docker compose down` (or `make docker-down`). Aggregate
workspaces persist in the Compose `workspaces` volume.

## Features

- **Identity-based dedup** — same file SHA1 across inputs → one entry
- **ID uniquification** — SPDX `SPDXRef-*` / CDX `bom-ref` / SPDX 3 IRI collision avoidance
- **Per-field provenance** — sidecar JSON tracking which input contributed each value
- **Conflict detection** — flags disagreements with first-writer resolution
- **Edit layer** — persistent user corrections that survive merge re-runs (Phase 3)

## Supported Formats

| Format | CLI `--format` | Auto-detection hint |
|--------|----------------|---------------------|
| CycloneDX 1.4 JSON | `cyclonedx` | `CYCLONEDX_JSON_*.json` or `"bomFormat": "CycloneDX"` |
| SPDX 2 tag-value | `spdx2tv` | `*.spdx` extension |
| DEP5 (Debian copyright) | `dep5` | `DEP5_*.txt` or `Format: https://www.debian.org/...` header |
| ReadMeOSS | `readmeoss` | `ReadMe_OSS_*.txt` or `====` separator header |
| SPDX 3 JSON | `spdx3json` | `SPDX3JSON_*.json` or top-level JSON array |
| CLIXML | `clixml` | `CLIXML_*.xml` or `<ComponentLicenseInformation` tag |

**Same-format merge only** — all inputs must be the same format. Cross-format conversion is not supported.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

### Basic command

```bash
report-aggregator merge <input-files...> -o <output-file> [--format <format>]
```

- **`<input-files...>`** — two or more report files from FOSSology (same format)
- **`-o`, `--output`** — path for the merged report (required)
- **`--format`** — optional format override when auto-detection fails or is ambiguous

Every merge produces two files:

| Output | Description |
|--------|-------------|
| `<output-file>` | The merged report in the same format as the inputs |
| `<output-file>.provenance.json` | Sidecar with input list, field provenance, and conflicts |

### CycloneDX 1.4 JSON

```bash
# Auto-detected from CYCLONEDX_JSON_* filename or bomFormat field
report-aggregator merge \
  CYCLONEDX_JSON_fckeditor-2.4.8.zip.json \
  CYCLONEDX_JSON_zlib132.zip.json \
  -o merged.cdx.json

# Explicit format
report-aggregator merge report-a.json report-b.json -o merged.json --format cyclonedx
```

### SPDX 2 tag-value

```bash
# Auto-detected from .spdx extension
report-aggregator merge \
  SPDX2TV_fckeditor-2.4.8.zip.spdx \
  SPDX2TV_zlib132.zip.spdx \
  -o merged.spdx

# Explicit format
report-aggregator merge report-a.spdx report-b.spdx -o merged.spdx --format spdx2tv
```

### DEP5 (Debian copyright)

```bash
# Auto-detected from DEP5_* filename or Format: header
report-aggregator merge \
  DEP5_fckeditor-2.4.8.zip.txt \
  DEP5_zlib132.zip.txt \
  -o merged-dep5.txt

# Explicit format (required when filename/content is ambiguous)
report-aggregator merge dep5-a.txt dep5-b.txt -o merged-dep5.txt --format dep5
```

### ReadMeOSS

```bash
# Auto-detected from ReadMe_OSS_* filename or === separator header
report-aggregator merge \
  ReadMe_OSS_fckeditor-2.4.8.zip.txt \
  ReadMe_OSS_zlib132.zip.txt \
  -o merged-readme.txt

# Explicit format (required when filename/content is ambiguous)
report-aggregator merge readme-a.txt readme-b.txt -o merged-readme.txt --format readmeoss
```

### SPDX 3 JSON

```bash
# Auto-detected from SPDX3JSON_* filename or JSON array structure
report-aggregator merge \
  SPDX3JSON_fckeditor-2.4.8.zip.json \
  SPDX3JSON_zlib132.zip.json \
  -o merged-spdx3.json

# Explicit format (required for generic .json names)
report-aggregator merge spdx3-a.json spdx3-b.json -o merged-spdx3.json --format spdx3json
```

### CLIXML (Component License Information XML)

```bash
# Auto-detected from CLIXML_* filename or <ComponentLicenseInformation tag
report-aggregator merge \
  CLIXML_fckeditor-2.4.8.zip.xml \
  CLIXML_zlib132.zip.xml \
  -o merged-clixml.xml

# Explicit format (required for generic .xml names)
report-aggregator merge report-a.xml report-b.xml -o merged.xml --format clixml
```

**CLIXML format specifics:**
- XML-based component license information format generated by FOSSology's `clixml` agent
- Contains comprehensive license, copyright, obligation, export restrictions, and patent information
- Component identity based on SHA1 hash (`componentSHA1` attribute)
- License/copyright deduplication by normalized text content (md5)
- Obligation deduplication includes topic, text, and associated licenses
- **Multi-root handling:** FOSSology's `uploadsAdd` concatenates multiple `<ComponentLicenseInformation>` roots in one file — the aggregator preserves this behavior
- "NA" values are normalized to empty strings before comparison to avoid false conflicts
- File hash formats support both plain (`abc123...`) and prefixed (`sha1:abc123...`) variations

### Merging three or more reports

```bash
report-aggregator merge upload-a.json upload-b.json upload-c.json -o merged-all.json
```

All inputs must share the same format. The tool deduplicates entries by content identity (SHA1 for files/packages, md5(text) for license blocks) and records which inputs contributed each value in the provenance sidecar.

### Format auto-detection

When `--format` is omitted, detection runs in this order:

1. **Filename prefix** — `DEP5_*`, `ReadMe_OSS_*`, `SPDX3JSON_*`, `CYCLONEDX_JSON_*`, `CLIXML_*`
2. **Content sniffing** — first bytes of the file (DEP5 `Format:` header, ReadMeOSS `====` separators, JSON array vs CycloneDX object, CLIXML `<ComponentLicenseInformation` tag)
3. **Extension** — `.spdx` → SPDX 2 tag-value

If detection fails (e.g. a generic `report.txt` or `report.xml` with no recognizable header), pass `--format` explicitly:

```bash
report-aggregator merge a.txt b.txt -o merged.txt --format dep5
report-aggregator merge a.txt b.txt -o merged.txt --format readmeoss
report-aggregator merge a.xml b.xml -o merged.xml --format clixml
```

### CLI help

```bash
report-aggregator --help
report-aggregator merge --help
```

### Example output

```text
Auto-detected format: cyclonedx
Merged 2 reports → merged.json
Provenance sidecar → merged.provenance.json
```

## Edit Layer (Phase 3)

The edit layer allows you to apply persistent corrections to merged reports that survive future re-merges. Edits are stored as [RFC-6902 JSON Patch](https://datatracker.ietf.org/doc/html/rfc6902) operations in the provenance sidecar.

### Why use the edit layer?

**Problem:** You merge two reports, manually fix an error in the output, then a new upload arrives. When you re-merge all three, your manual correction is lost.

**Solution:** Apply corrections via the `edit` command. The edit is recorded in the provenance sidecar and automatically replayed on every re-merge.

### Workflow example

```bash
# 1. Initial merge
report-aggregator merge report-a.json report-b.json -o merged.json

# 2. Discover an error in the merged output
# Instead of manually editing merged.json, use the edit command:

report-aggregator edit merged.json \
  --patch '{"op": "replace", "path": "/metadata/component/copyright", "value": "Copyright 2024 Acme Corp"}' \
  --who "maintainer@example.com" \
  --reason "Fixed copyright year"

# 3. New input arrives, re-merge all reports
report-aggregator merge report-a.json report-b.json report-c.json -o merged.json

# ✓ Your correction is automatically replayed!
# The edit survives the re-merge because it's stored in merged.provenance.json
```

### Edit commands

#### `edit` - Apply a correction

```bash
report-aggregator edit <merged-file> \
  --patch '<json-patch-operation>' \
  --who '<user-identifier>' \
  --reason '<explanation>'
```

**RFC-6902 operations supported:**
- `add` - Add a new field
- `remove` - Delete a field
- `replace` - Change a value
- `move` - Move a value to a different path
- `copy` - Copy a value to another path
- `test` - Assert a value (for safety)

**Examples:**

```bash
# Replace a copyright field
report-aggregator edit merged.json \
  --patch '{"op": "replace", "path": "/packages/0/PackageCopyrightText", "value": "© 2024"}' \
  --who "alice@example.com"

# Add a missing license
report-aggregator edit merged.spdx \
  --patch '{"op": "add", "path": "/packages/0/LicenseConcluded", "value": "MIT"}' \
  --reason "Scanner missed obvious MIT license"

# Remove an incorrect entry
report-aggregator edit merged.json \
  --patch '{"op": "remove", "path": "/components/5"}' \
  --who "bob@example.com" \
  --reason "Duplicate component"
```

#### `list-edits` - Show edit history

```bash
report-aggregator list-edits <merged-file>
```

Displays all edits with timestamps, users, operations, and reasons.

**Example output:**
```
Edit History for merged.json (2 edits)

1. [2026-06-17 10:30:00] alice@example.com
   Operation: replace
   Path: /packages/0/PackageCopyrightText
   Reason: Fixed copyright year

2. [2026-06-17 14:15:00] bob@example.com
   Operation: remove
   Path: /components/5
   Reason: Duplicate component
```

#### `undo` - Remove an edit

```bash
# Undo last edit
report-aggregator undo <merged-file>

# Undo specific edit by index (1-based)
report-aggregator undo <merged-file> --index 2
```

After undoing, re-run the original merge command to apply the change. The remaining edits will be replayed automatically.

#### `replay` - Manually re-apply edits

```bash
report-aggregator replay <merged-file>
```

Useful if you manually edited the file and want to re-apply the recorded edits from the provenance sidecar.

### How it works

1. **Edits are stored** in the `.provenance.json` sidecar as RFC-6902 patches
2. **Every merge checks** for an existing provenance file at the output path
3. **Patches are replayed** automatically after merging but before rendering
4. **Failed patches are skipped** with warnings (structure may have changed)
5. **Edit history is preserved** across all re-merges

### JSON Patch paths

Paths use [JSON Pointer](https://datatracker.ietf.org/doc/html/rfc6901) notation (`/path/to/field`). To determine the correct path:

1. Load the merged file to inspect its structure
2. For CycloneDX: `/metadata/component/copyright`, `/components/0/licenses/0`
3. For SPDX 2: `/packages/0/PackageName`, `/files/0/LicenseConcluded`
4. For DEP5: `/stanzas/0/Copyright`
5. For ReadMeOSS: `/sections/0/blocks/0/text`
6. For SPDX 3: `/by_id/<spdx-id>/name`

### Troubleshooting

**"Patch path does not exist"**: The structure changed since the edit was created. Common when:
- Files were removed from inputs
- Re-ordering happened during merge
- Edit path referenced a field that no longer exists

**Solution:** View edit history with `list-edits`, identify the failing edit, `undo` it, inspect the new structure, and re-apply with the correct path.

**Edit not taking effect**: Ensure you re-run the merge command after applying edits. Edits are stored in the provenance sidecar but only applied during merge.

## HTTP API (for the web UI)

An optional FastAPI service exposes the merge/edit engine over HTTP for the
[`frontend/`](frontend/) Next.js front-end. It reuses the
engine in-process (no CLI shell-out).

Install the API extra and run the service:

```bash
pip install -e ".[api]"
python -m report_aggregator.api          # http://127.0.0.1:8000
```

The `api` extra includes [`fossology`](https://fossology.github.io/fossology-python/)
(fossology-python) for the FOSSology Integrations feature (import existing uploads).
TLS certificate verification is always enabled for that connection.

Key endpoints (all under `/api`):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| POST | `/merge` | Multipart upload of input files (+ optional `format`); returns an `aggregate_id` |
| GET | `/reports` | List aggregates |
| GET | `/reports/{id}` | Aggregate summary + counts |
| GET | `/reports/{id}/fields` | Flattened field tree with provenance + conflicts |
| GET | `/reports/{id}/raw` | Merged report text |
| GET | `/reports/{id}/download` | Download merged report as a file |
| GET | `/reports/{id}/provenance/download` | Download the provenance sidecar |
| GET | `/reports/{id}/inputs/{idx}/raw` | A single input's text |
| GET | `/reports/{id}/conflicts` | Detected conflicts |
| GET/POST | `/reports/{id}/edits` | List or apply RFC-6902 edits |
| PUT | `/reports/{id}/document` | Replace the whole document (editor); diffed into recorded patches |
| DELETE | `/reports/{id}/edits/{index}` | Undo an edit (re-merge + replay) |

Workspaces are stored under ``<report-aggregator>/.api_workspaces`` by
default (always inside this repository, not the shell's working directory).
Override with ``REPORT_AGGREGATOR_WORKSPACE`` (relative paths resolve under the
project root; absolute paths are used as-is, mainly for tests).

The interactive editor save path (``PUT /reports/{id}/document``) validates and
structurally diffs every save regardless of size.  For very large documents the
post-apply deepcopy re-verification step is skipped to avoid excessive memory
usage; only the verification is skipped — the granular RFC-6902 patches are
always computed and recorded in provenance.  The threshold is controlled by:

``REPORT_AGGREGATOR_DIFF_VERIFY_MAX_BYTES`` — content larger than this (bytes)
skips the deepcopy re-check.  Default: ``26214400`` (25 MB).

> **Security:** the service has no authentication and permissive CORS for
> `localhost:3000`. It is intended for local development only.

## Testing

```bash
pytest tests/ -v
```

Fixtures from real FOSSology exports live under `tests/fixtures/fossology-reports/`.

## License

MIT
