/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Search, History, AlertTriangle, Download } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { buildSourceColors } from "@/lib/colors";
import { formatLabel, shortId } from "@/lib/format";
import { SourceLegend } from "@/components/viewer/source-legend";
import { VirtualizedFieldTree } from "@/components/viewer/virtualized-field-tree";
import { EditFieldDialog } from "@/components/viewer/edit-field-dialog";
import { RawDiff } from "@/components/viewer/raw-diff";
import { DocumentEditor } from "@/components/viewer/document-editor";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

const VIEW_TABS = [
  ["fields", "Fields"],
  ["raw", "Raw / diff"],
  ["editor", "Editor"],
];

export default function ReportViewerPage() {
  const params = useParams();
  const id = params.id;

  const [report, setReport] = React.useState(null);
  const [tree, setTree] = React.useState(null);
  const [edits, setEdits] = React.useState([]);
  const [headerStatus, setHeaderStatus] = React.useState("loading");
  const [fieldsStatus, setFieldsStatus] = React.useState("loading");
  const [term, setTerm] = React.useState("");
  const [mode, setMode] = React.useState("all");
  const [editingNode, setEditingNode] = React.useState(null);
  const [savingEdit, setSavingEdit] = React.useState(false);
  const [view, setView] = React.useState("fields");

  const load = React.useCallback(async () => {
    setHeaderStatus("loading");
    setFieldsStatus("loading");
    setTree(null);

    try {
      const [r, e] = await Promise.all([api.getReport(id), api.getEdits(id)]);
      setReport(r);
      setEdits(e.edits || []);
      setHeaderStatus("ready");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load report";
      toast.error(msg);
      setHeaderStatus("error");
      setFieldsStatus("error");
      return;
    }

    try {
      const t = await api.getFields(id);
      setTree(t);
      setFieldsStatus("ready");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load fields";
      toast.error(msg);
      setFieldsStatus("error");
    }
  }, [id]);

  React.useEffect(() => {
    load();
  }, [load]);

  const colors = React.useMemo(() => buildSourceColors(tree?.sources || []), [tree]);
  const editedPaths = React.useMemo(
    () => new Set(edits.map((e) => e.patch?.path).filter(Boolean)),
    [edits]
  );

  const visibleNodes = React.useMemo(() => {
    if (!tree) return [];
    const t = term.trim().toLowerCase();
    return tree.nodes.filter((n) => {
      if (mode === "conflicts" && !n.conflict) return false;
      if (mode === "edited" && !editedPaths.has(n.path)) return false;
      if (!t) return true;
      return (
        (n.key && String(n.key).toLowerCase().includes(t)) ||
        (n.value != null && String(n.value).toLowerCase().includes(t)) ||
        (n.path && n.path.toLowerCase().includes(t))
      );
    });
  }, [tree, term, mode, editedPaths]);

  async function handleSaveEdit(edit) {
    const path = edit.path;
    const prevTree = tree;
    setSavingEdit(true);
    setTree((t) =>
      t
        ? {
            ...t,
            nodes: t.nodes.map((n) =>
              n.path === path ? { ...n, value: edit.value } : n
            ),
          }
        : t
    );
    try {
      const result = await api.applyEdit(id, edit);
      toast.success("Edit applied.");
      setEditingNode(null);
      const [t, e] = await Promise.all([api.getFields(id), api.getEdits(id)]);
      setReport((r) => (r ? { ...r, counts: result.counts ?? r.counts } : r));
      setTree(t);
      setEdits(e.edits || []);
    } catch (err) {
      setTree(prevTree);
      const msg = err instanceof ApiError ? err.message : "Edit failed";
      toast.error(msg);
    } finally {
      setSavingEdit(false);
    }
  }

  if (headerStatus === "loading") {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (headerStatus === "error") {
    return (
      <Alert variant="error">
        <AlertDescription>Could not load this report.</AlertDescription>
      </Alert>
    );
  }

  const conflictCount = report?.counts?.conflicts ?? 0;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="mb-1 flex items-center gap-2 text-2xl font-bold text-foreground">
            Merged Report
            <Badge>{formatLabel(report.format)}</Badge>
          </h1>
          <span className="font-mono text-xs text-muted-foreground">{shortId(id)}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="md" asChild>
            <a href={api.downloadUrl(id)} download>
              <Download className="h-4 w-4" />
              Download
            </a>
          </Button>
          <Button
            variant="outline"
            size="md"
            asChild
            className={conflictCount > 0 ? "border-warning-500 text-warning-600" : undefined}
          >
            <Link href={`/reports/${id}/conflicts`}>
              <AlertTriangle className="h-4 w-4" />
              Conflicts ({conflictCount})
            </Link>
          </Button>
          <Button variant="outline" size="md" asChild>
            <Link href={`/reports/${id}/history`}>
              <History className="h-4 w-4" />
              History ({edits.length})
            </Link>
          </Button>
        </div>
      </div>

      <nav className="mb-4 flex gap-0 border-b-2 border-brand-900">
        {VIEW_TABS.map(([v, label]) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={cn(
              "border border-b-0 border-border px-4 py-2 text-sm font-medium transition-colors",
              "rounded-t first:ml-0",
              view === v
                ? "border-b-0 bg-white text-primary"
                : "bg-neutral-100 text-foreground hover:bg-neutral-200"
            )}
          >
            {label}
          </button>
        ))}
      </nav>

      {view === "fields" && (
        <>
          <Card className="mb-4 py-4">
            <CardContent>
              {tree ? (
                <SourceLegend sources={tree.sources} colors={colors} />
              ) : (
                <p className="text-muted-foreground">Loading field sources…</p>
              )}
              <div className="mt-3 flex flex-wrap gap-3">
                <div className="relative min-w-[200px] flex-1">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search keys, values, or paths…"
                    value={term}
                    onChange={(e) => setTerm(e.target.value)}
                    disabled={fieldsStatus !== "ready"}
                    className="pl-8"
                  />
                </div>
                <Select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  disabled={fieldsStatus !== "ready"}
                  aria-label="filter"
                  className="w-auto min-w-[140px]"
                >
                  <option value="all">All fields</option>
                  <option value="conflicts">Conflicts only</option>
                  <option value="edited">Edited only</option>
                </Select>
              </div>
              {tree?.truncated && (
                <p className="mt-2 text-xs text-warning-600">
                  Field tree truncated for display. Use search to narrow results.
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="overflow-hidden py-0">
            {fieldsStatus === "loading" && (
              <p className="p-4 text-muted-foreground">Loading fields…</p>
            )}
            {fieldsStatus === "error" && (
              <Alert variant="error" className="m-4">
                <AlertDescription>Could not load fields.</AlertDescription>
              </Alert>
            )}
            {fieldsStatus === "ready" && visibleNodes.length === 0 && (
              <p className="p-4 text-muted-foreground">No matching fields.</p>
            )}
            {fieldsStatus === "ready" && visibleNodes.length > 0 && (
              <VirtualizedFieldTree
                nodes={visibleNodes}
                colors={colors}
                editedPaths={editedPaths}
                onEdit={setEditingNode}
              />
            )}
          </Card>
        </>
      )}

      {view === "raw" && <RawDiff id={id} inputs={report.inputs || []} />}
      {view === "editor" && (
        <DocumentEditor id={id} format={report.format} onSaved={load} />
      )}

      <EditFieldDialog
        node={editingNode}
        open={!!editingNode}
        submitting={savingEdit}
        onClose={() => setEditingNode(null)}
        onSubmit={handleSaveEdit}
      />
    </div>
  );
}
