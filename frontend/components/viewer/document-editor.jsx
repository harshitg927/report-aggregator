/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { toast } from "sonner";
import { Save, RotateCcw, Loader2 } from "lucide-react";
import {
  SearchQuery,
  findNext,
  findPrevious,
  highlightSelectionMatches,
  searchKeymap,
  setSearchQuery,
} from "@codemirror/search";
import { keymap } from "@codemirror/view";
import { api, ApiError } from "@/lib/api";
import { countMatches } from "@/lib/text-search";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TextSearchBar } from "@/components/viewer/text-search-bar";

const CodeMirror = dynamic(() => import("@uiw/react-codemirror"), {
  ssr: false,
  loading: () => (
    <div className="p-4 text-sm text-muted-foreground">Loading editor…</div>
  ),
});

const SEARCH_EXTENSIONS = [highlightSelectionMatches(), keymap.of(searchKeymap)];

// Files larger than this get plain-text mode (no syntax highlighting / validation
// extensions) so the editor stays responsive. Editing and save are always enabled.
const HIGHLIGHT_MAX_BYTES =
  parseInt(process.env.NEXT_PUBLIC_EDITOR_HIGHLIGHT_MAX_BYTES || "", 10) ||
  2 * 1024 * 1024; // 2 MB default

async function languageExtensions(format) {
  try {
    if (format === "cyclonedx" || format === "spdx3json") {
      const { json } = await import("@codemirror/lang-json");
      return [json()];
    }
    if (format === "clixml") {
      const { xml } = await import("@codemirror/lang-xml");
      return [xml()];
    }
  } catch {
    // language support is optional — silently fall back to plain text
  }
  return [];
}

export function DocumentEditor({ id, format, onSaved }) {
  // Size probe — used only to decide whether to load language extensions.
  // If it fails, we stay in plain-text mode (size = 0 fallback keeps editing enabled).
  const [fileSize, setFileSize] = React.useState(null);
  const [sizeLoading, setSizeLoading] = React.useState(true);

  React.useEffect(() => {
    let active = true;
    setSizeLoading(true);
    api
      .getRawMeta(id, "merged")
      .then((m) => { if (active) setFileSize(m.size); })
      .catch(() => { if (active) setFileSize(0); })
      .finally(() => { if (active) setSizeLoading(false); });
    return () => { active = false; };
  }, [id]);

  const [original, setOriginal] = React.useState("");
  const [value, setValue] = React.useState("");
  const [who, setWho] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [contentLoading, setContentLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [extensions, setExtensions] = React.useState([]);
  const [search, setSearch] = React.useState("");
  const editorViewRef = React.useRef(null);

  // Load the full document text.
  React.useEffect(() => {
    let active = true;
    setContentLoading(true);
    api
      .getRaw(id)
      .then((text) => {
        if (!active) return;
        setOriginal(text);
        setValue(text);
      })
      .catch((err) => {
        toast.error(err instanceof ApiError ? err.message : "Failed to load document");
      })
      .finally(() => { if (active) setContentLoading(false); });
    return () => { active = false; };
  }, [id]);

  // Load language extensions only for small files.
  React.useEffect(() => {
    if (fileSize === null) return; // wait until probe completes
    if (fileSize > HIGHLIGHT_MAX_BYTES) {
      setExtensions([]); // plain-text mode
    } else {
      languageExtensions(format).then(setExtensions);
    }
  }, [format, fileSize]);

  // Wire the CodeMirror search query whenever the search term changes.
  React.useEffect(() => {
    const view = editorViewRef.current;
    if (!view) return;
    const query = new SearchQuery({
      search,
      caseSensitive: false,
      literal: false,
      regexp: false,
      wholeWord: false,
    });
    view.dispatch({ effects: setSearchQuery.of(query) });
  }, [search, value]);

  const loading = sizeLoading || contentLoading;
  const isLargeFile = fileSize !== null && fileSize > HIGHLIGHT_MAX_BYTES;
  const dirty = value !== original;
  const matchCount = search.trim() ? countMatches(value, search) : 0;

  function goToNextMatch() {
    const view = editorViewRef.current;
    if (view) findNext(view);
  }

  function goToPrevMatch() {
    const view = editorViewRef.current;
    if (view) findPrevious(view);
  }

  async function save() {
    if (!dirty) {
      toast.info("No changes to save.");
      return;
    }
    setSaving(true);
    try {
      const res = await api.saveDocument(id, {
        content: value,
        who: who.trim() || "user",
        reason: reason.trim() || "Edited via interactive editor",
      });
      toast.success(
        res.changes > 0
          ? `Saved — ${res.changes} change(s) recorded.`
          : "Saved."
      );
      setOriginal(value);
      onSaved?.();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="h-64 animate-pulse rounded-lg border bg-muted/40" />;
  }

  const searchHint =
    search.trim() && matchCount === 0
      ? "No matches in the document."
      : search.trim()
        ? `${matchCount} match(es). Use arrows or Ctrl+G / Ctrl+Shift+G.`
        : null;

  return (
    <div className="space-y-4">
      {/* Large-file notice — editing is still enabled */}
      {isLargeFile && (
        <div className="rounded border border-warning-500/30 bg-warning-100 px-4 py-2 text-sm text-warning-700">
          Large document ({(fileSize / 1_048_576).toFixed(1)} MB) — syntax
          highlighting is off for performance. Editing and save are fully
          enabled.
        </div>
      )}

      {/* Who / Reason / Save controls */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="editor-who">Who</Label>
          <Input
            id="editor-who"
            placeholder="you@example.com"
            value={who}
            onChange={(e) => setWho(e.target.value)}
            className="w-56"
          />
        </div>
        <div className="space-y-1 flex-1 min-w-[200px]">
          <Label htmlFor="editor-reason">Reason</Label>
          <Input
            id="editor-reason"
            placeholder="Why this change?"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setValue(original)}
            disabled={!dirty || saving}
            className="gap-1"
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </Button>
          <Button onClick={save} disabled={!dirty || saving} className="gap-1">
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      <TextSearchBar
        id="editor-search"
        value={search}
        onChange={setSearch}
        placeholder="Search in document…"
        hint={searchHint}
        showNav={!!search.trim() && matchCount > 0}
        onNext={goToNextMatch}
        onPrev={goToPrevMatch}
      />

      <p className="text-xs text-muted-foreground">
        Changes are validated, diffed, and recorded in the edit history so they
        survive re-merges.{" "}
        {dirty && <span className="text-warning-600">Unsaved changes.</span>}
      </p>

      <div className="overflow-hidden rounded-md border text-sm">
        <CodeMirror
          value={value}
          height="60vh"
          theme="light"
          extensions={[...extensions, ...SEARCH_EXTENSIONS]}
          onCreateEditor={(view) => { editorViewRef.current = view; }}
          onChange={(v) => setValue(v)}
        />
      </div>
    </div>
  );
}
