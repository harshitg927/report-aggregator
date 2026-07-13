"use client";

import * as React from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { TextSearchBar } from "@/components/viewer/text-search-bar";
import { VirtualizedDiff } from "@/components/viewer/virtualized-diff";

const SEARCH_DEBOUNCE_MS = 350;

export function RawDiff({ id, inputs = [] }) {
  const options = React.useMemo(
    () => [
      { key: "merged", label: "Merged output" },
      ...inputs
        .slice()
        .sort((a, b) => a.input_index - b.input_index)
        .map((i) => ({ key: `input:${i.input_index}`, label: `input: ${i.source_id}` })),
    ],
    [inputs]
  );

  const [left, setLeft] = React.useState(options[1]?.key ?? "merged");
  const [right, setRight] = React.useState("merged");

  // Diff meta
  const [diffMeta, setDiffMeta] = React.useState(null);
  const [metaLoading, setMetaLoading] = React.useState(false);

  // Search state
  const [search, setSearch] = React.useState("");
  const [matches, setMatches] = React.useState([]); // [{row, side, line_no}]
  const [matchCursor, setMatchCursor] = React.useState(-1);
  const [searchTruncated, setSearchTruncated] = React.useState(false);
  const [highlightRow, setHighlightRow] = React.useState(null);

  // Load diff meta whenever the source pair changes.
  React.useEffect(() => {
    let active = true;
    setDiffMeta(null);
    setMetaLoading(true);
    setSearch("");
    setMatches([]);
    setMatchCursor(-1);
    setHighlightRow(null);
    api
      .getDiffMeta(id, left, right)
      .then((m) => { if (active) setDiffMeta(m); })
      .catch((err) => {
        toast.error(err instanceof ApiError ? err.message : "Failed to load diff");
      })
      .finally(() => { if (active) setMetaLoading(false); });
    return () => { active = false; };
  }, [id, left, right]);

  // Debounced search — fires the backend search whenever the query changes.
  React.useEffect(() => {
    if (!search.trim()) {
      setMatches([]);
      setMatchCursor(-1);
      setHighlightRow(null);
      return;
    }
    const timer = setTimeout(() => {
      api
        .searchDiff(id, left, right, search.trim())
        .then((res) => {
          setMatches(res.matches);
          setSearchTruncated(res.truncated);
          const cursor = res.matches.length > 0 ? 0 : -1;
          setMatchCursor(cursor);
          setHighlightRow(cursor >= 0 ? res.matches[cursor].row : null);
        })
        .catch((err) => {
          toast.error(err instanceof ApiError ? err.message : "Search failed");
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [id, left, right, search]);

  // Navigate to next/prev match.
  function goNext() {
    if (!matches.length) return;
    const next = (matchCursor + 1) % matches.length;
    setMatchCursor(next);
    setHighlightRow(matches[next].row);
  }

  function goPrev() {
    if (!matches.length) return;
    const prev = (matchCursor - 1 + matches.length) % matches.length;
    setMatchCursor(prev);
    setHighlightRow(matches[prev].row);
  }

  const searchHint = React.useMemo(() => {
    if (!search.trim()) return null;
    if (matches.length === 0) return "No matches.";
    const cursor = matchCursor >= 0 ? `${matchCursor + 1} of ` : "";
    const truncNote = searchTruncated ? " (results capped)" : "";
    return `${cursor}${matches.length} match(es)${truncNote}`;
  }, [search, matches, matchCursor, searchTruncated]);

  return (
    <div className="space-y-4">
      {/* Source selectors */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="diff-left">Left</Label>
          <Select
            id="diff-left"
            aria-label="diff left"
            value={left}
            onChange={(e) => setLeft(e.target.value)}
            className="w-auto"
          >
            {options.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="diff-right">Right</Label>
          <Select
            id="diff-right"
            aria-label="diff right"
            value={right}
            onChange={(e) => setRight(e.target.value)}
            className="w-auto"
          >
            {options.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </Select>
        </div>
        {diffMeta && (
          <p className="text-xs text-muted-foreground self-end">
            {diffMeta.total_rows.toLocaleString()} rows
            {" · "}+{(diffMeta.counts.insert + diffMeta.counts.replace).toLocaleString()}
            {" "}−{(diffMeta.counts.delete + diffMeta.counts.replace).toLocaleString()}
          </p>
        )}
      </div>

      {/* VS Code-style find bar */}
      <TextSearchBar
        id="raw-diff-search"
        value={search}
        onChange={setSearch}
        placeholder="Find in diff…"
        hint={searchHint}
        showNav={matches.length > 0}
        onNext={goNext}
        onPrev={goPrev}
      />

      {/* Diff viewer */}
      <div className="overflow-hidden rounded-md border text-xs">
        {metaLoading && (
          <p className="p-4 text-sm text-muted-foreground">Computing diff…</p>
        )}
        {!metaLoading && diffMeta && (
          <VirtualizedDiff
            id={id}
            left={left}
            right={right}
            totalRows={diffMeta.total_rows}
            highlightRow={highlightRow}
          />
        )}
      </div>
    </div>
  );
}
