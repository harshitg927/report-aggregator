# Report Aggregator

Merge N FOSSology-generated reports into one deduplicated report of the same format.

## Features

- **Identity-based dedup** — same file SHA1 across inputs → one entry
- **ID uniquification** — SPDX `SPDXRef-*` / CDX `bom-ref` collision avoidance
- **Per-field provenance** — sidecar JSON tracking which input contributed each value
- **Conflict detection** — flags disagreements with first-writer resolution

## Supported Formats

| Format | Status |
|--------|--------|
| CycloneDX 1.4 JSON | Phase 1 |
| SPDX 2 tag-value | Phase 1 |
| DEP5 | Phase 2 |
| ReadMeOSS | Phase 2 |
| SPDX 3 JSON | Phase 2 |
| CLIXML | Phase 4 |

## Usage

```bash
# Merge two CycloneDX reports
report-aggregator merge report-a.json report-b.json -o merged.json

# Merge two SPDX 2 tag-value reports
report-aggregator merge report-a.spdx report-b.spdx -o merged.spdx

# Output: merged file + merged.provenance.json sidecar
```

## Installation

```bash
pip install -e ".[dev]"
```

## Testing

```bash
pytest tests/ -v
```

## License

MIT
