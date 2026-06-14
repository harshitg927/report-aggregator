# Report Aggregator

Merge N FOSSology-generated reports into one deduplicated report of the same format.

## Features

- **Identity-based dedup** — same file SHA1 across inputs → one entry
- **ID uniquification** — SPDX `SPDXRef-*` / CDX `bom-ref` / SPDX 3 IRI collision avoidance
- **Per-field provenance** — sidecar JSON tracking which input contributed each value
- **Conflict detection** — flags disagreements with first-writer resolution

## Supported Formats

| Format | CLI `--format` | Auto-detection hint |
|--------|----------------|---------------------|
| CycloneDX 1.4 JSON | `cyclonedx` | `CYCLONEDX_JSON_*.json` or `"bomFormat": "CycloneDX"` |
| SPDX 2 tag-value | `spdx2tv` | `*.spdx` extension |
| DEP5 (Debian copyright) | `dep5` | `DEP5_*.txt` or `Format: https://www.debian.org/...` header |
| ReadMeOSS | `readmeoss` | `ReadMe_OSS_*.txt` or `====` separator header |
| SPDX 3 JSON | `spdx3json` | `SPDX3JSON_*.json` or top-level JSON array |
| CLIXML | — | Phase 4 (not yet implemented) |

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

### Merging three or more reports

```bash
report-aggregator merge upload-a.json upload-b.json upload-c.json -o merged-all.json
```

All inputs must share the same format. The tool deduplicates entries by content identity (SHA1 for files/packages, md5(text) for license blocks) and records which inputs contributed each value in the provenance sidecar.

### Format auto-detection

When `--format` is omitted, detection runs in this order:

1. **Filename prefix** — `DEP5_*`, `ReadMe_OSS_*`, `SPDX3JSON_*`, `CYCLONEDX_JSON_*`
2. **Content sniffing** — first bytes of the file (DEP5 `Format:` header, ReadMeOSS `====` separators, JSON array vs CycloneDX object)
3. **Extension** — `.spdx` → SPDX 2 tag-value

If detection fails (e.g. a generic `report.txt` with no recognizable header), pass `--format` explicitly:

```bash
report-aggregator merge a.txt b.txt -o merged.txt --format dep5
report-aggregator merge a.txt b.txt -o merged.txt --format readmeoss
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

## Testing

```bash
pytest tests/ -v
```

Fixtures from real FOSSology exports live under `tests/fixtures/fossology-reports/`.

## License

MIT
