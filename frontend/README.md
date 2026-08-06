<!-- SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

     SPDX-License-Identifier: MIT
-->

# Report Aggregator — Frontend

A Next.js (App Router, JavaScript) front-end for the
[`report-aggregator`](..) engine. It lets you merge multiple
FOSSology reports and inspect the result in a **transparent, editable view**:
every field shows which input contributed it, conflicts are surfaced, and edits
are persisted through the engine's RFC-6902 edit layer so they survive
re-merges.

> **Note:** This directory (`frontend/`) lives inside the
> [`report-aggregator`](..) monorepo. Both the Python engine and this UI are
> developed and tracked together.

## Features

- **Reports dashboard** — browse all merged aggregates with input/conflict/edit counts.
- **Merge wizard** — drag-and-drop two or more same-format reports, with an optional format override.
- **Transparent viewer** — a flattened field tree where each value carries
  colour-coded provenance badges and conflicts open a popover showing every
  input's value and the chosen resolution.
- **Inline editing** — click any leaf to edit it; the change becomes an
  RFC-6902 patch (`replace`) recorded with who/reason and applied optimistically.
- **Interactive editor** — edit the full merged document in a CodeMirror editor;
  on save it is validated, diffed against the current document, and the
  difference is recorded as RFC-6902 patches so it stays in the edit history and
  replays on re-merge.
- **Download** — download the merged report (and its provenance sidecar) as files.
- **Raw / diff toggle** — view the merged output or diff any input against
  another input or the merged result.
- **Edit history** — an audit trail of every edit with one-click undo (re-merge + replay).
- **Conflicts page** — all detected conflicts with per-source values and the chosen value.
- Dark mode, in-report search/filter, and toast notifications.

## Architecture

```
frontend/ (Next.js)  ──HTTP──▶  report-aggregator API (FastAPI)  ──▶  merge/edit engine
```

The UI never runs the Python engine directly; it talks to the FastAPI service
that wraps the engine in-process.

## Prerequisites

- Node.js 18+ and npm
- Python 3.11+ with the backend installed including the API extra:

  ```bash
  cd ..
  pip install -e ".[api,dev]"   # add --break-system-packages on PEP-668 systems
  ```

## Configuration

The UI reads the API base URL from `NEXT_PUBLIC_API_BASE_URL`. Copy the example
and adjust if needed:

```bash
cp .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Running

Install dependencies, then start both services.

```bash
npm install
```

Start the API (from the monorepo root):

```bash
cd ..
python3 -m report_aggregator.api          # serves http://127.0.0.1:8000
```

Start the UI (from this directory):

```bash
npm run dev                                # serves http://localhost:3000
```

Or launch both together from this directory (the script resolves the backend
as the parent directory `..`; override with `REPORT_AGGREGATOR_DIR`):

```bash
npm run dev:all
```

You can also use the root `Makefile` from the monorepo root:

```bash
make dev-api    # terminal 1
make dev-ui     # terminal 2
# or:
make dev-all    # both via dev.sh
```

## Testing

```bash
npm test          # vitest component/interaction tests
npm run build     # production build
```

## Security note

The FastAPI service is a **local development service**. It has **no
authentication or access control** and uses permissive CORS for
`localhost:3000`. Do not expose it to a public network without adding
authentication and tightening CORS. Uploaded reports and merged outputs are
stored unencrypted on disk under the API workspace directory inside the
monorepo root (default: `.api_workspaces/`).
