"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Undo2, Pencil } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { editMatchesSearch } from "@/lib/text-search";
import { EditSummary } from "@/components/viewer/edit-summary";
import { TextSearchBar } from "@/components/viewer/text-search-bar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable, DataTableRow, DataTableCell } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";

export default function HistoryPage() {
  const { id } = useParams();
  const [edits, setEdits] = React.useState([]);
  const [status, setStatus] = React.useState("loading");
  const [undoing, setUndoing] = React.useState(null);
  const [search, setSearch] = React.useState("");

  const load = React.useCallback(async () => {
    setStatus("loading");
    try {
      const e = await api.getEdits(id);
      setEdits(e.edits || []);
      setStatus("ready");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load edits";
      toast.error(msg);
      setStatus("error");
    }
  }, [id]);

  React.useEffect(() => {
    load();
  }, [load]);

  const filteredEdits = React.useMemo(() => {
    const term = search.trim();
    if (!term) return edits;
    return edits.filter((e) => editMatchesSearch(e, term));
  }, [edits, search]);

  async function undo(oneBasedIndex) {
    if (!window.confirm("Remove this edit and re-merge? This replays remaining edits.")) return;
    setUndoing(oneBasedIndex);
    try {
      await api.undoEdit(id, oneBasedIndex);
      toast.success("Edit undone.");
      await load();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Undo failed";
      toast.error(msg);
    } finally {
      setUndoing(null);
    }
  }

  return (
    <div className="w-full">
      <PageHeader
        title="Edit History"
        actions={
          <Button asChild variant="link" size="sm" className="h-auto px-0">
            <Link href={`/reports/${id}`}>← Back to report</Link>
          </Button>
        }
      />

      {status === "loading" && (
        <p className="text-muted-foreground">Loading…</p>
      )}

      {status === "ready" && edits.length === 0 && (
        <Card>
          <CardContent className="py-6 text-center text-muted-foreground">
            No edits have been applied to this report.
          </CardContent>
        </Card>
      )}

      {status === "ready" && edits.length > 0 && (
        <>
          <div className="mb-4">
            <TextSearchBar
              id="history-search"
              value={search}
              onChange={setSearch}
              placeholder="Search who, change, path, reason…"
              hint={
                search.trim()
                  ? `Showing ${filteredEdits.length} of ${edits.length} edit(s).`
                  : null
              }
            />
          </div>

          {filteredEdits.length === 0 ? (
            <Card>
              <CardContent className="py-6 text-center text-muted-foreground">
                No edits match your search.
              </CardContent>
            </Card>
          ) : (
            <DataTable
              columns={["#", "Operation", "Path", "Change", "By", "When", ""]}
              className="table-fixed"
            >
              {filteredEdits.map((e) => {
                const idx = edits.indexOf(e) + 1;
                return (
                  <DataTableRow key={idx} className="align-top">
                    <DataTableCell className="w-[3%]">{idx}</DataTableCell>
                    <DataTableCell className="w-[7%]">
                      <Badge className="inline-flex items-center gap-1">
                        <Pencil className="h-3 w-3" />
                        {e.patch?.op}
                      </Badge>
                    </DataTableCell>
                    <DataTableCell className="w-[16%] min-w-0 max-w-0 break-all font-mono text-xs">
                      {e.patch?.path}
                    </DataTableCell>
                    <DataTableCell className="min-w-0 break-words">
                      <EditSummary edit={e} />
                    </DataTableCell>
                    <DataTableCell
                      className="w-[14%] min-w-0 max-w-0 break-all text-xs"
                      title={e.who || "user"}
                    >
                      {e.who || "user"}
                    </DataTableCell>
                    <DataTableCell className="w-[12%] whitespace-nowrap">
                      {formatDate(e.when)}
                    </DataTableCell>
                    <DataTableCell className="w-[7%]">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={undoing !== null}
                        onClick={() => undo(idx)}
                      >
                        <Undo2 className="h-3 w-3" />
                        {undoing === idx ? "Undoing…" : "Undo"}
                      </Button>
                    </DataTableCell>
                  </DataTableRow>
                );
              })}
            </DataTable>
          )}
        </>
      )}
    </div>
  );
}
