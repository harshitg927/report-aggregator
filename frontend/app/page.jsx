"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { GitMerge, AlertTriangle, Pencil, Plus, Search } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { FORMAT_LABELS, formatLabel, formatDate, shortId } from "@/lib/format";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { HoverPopover } from "@/components/ui/hover-popover";
import { PageHeader } from "@/components/page-header";
import { DataTable, DataTableRow, DataTableCell } from "@/components/data-table";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

function InputsCell({ report }) {
  const inputs = (report.inputs || []).slice().sort((a, b) => a.input_index - b.input_index);
  const count = report.counts?.inputs ?? inputs.length;

  const trigger = (
    <span
      aria-label={`View ${count} merged inputs`}
      className="inline-flex cursor-default items-center gap-1 rounded px-1 py-0.5 hover:bg-black/5"
    >
      <GitMerge className="h-3.5 w-3.5" />
      {count}
    </span>
  );

  if (inputs.length === 0) {
    return trigger;
  }

  return (
    <HoverPopover
      width="20rem"
      maxHeight="14rem"
      content={
        <div className="text-sm">
          <p className="mb-1.5 font-semibold">Merged inputs</p>
          <ul className="m-0 list-none p-0">
            {inputs.map((inp, idx) => (
              <li
                key={`${inp.input_index}-${inp.source_id}`}
                className={cn(
                  idx < inputs.length - 1 && "mb-2 border-b border-border pb-2"
                )}
              >
                <div className="mb-0.5 text-xs text-muted-foreground">
                  Input {inp.input_index + 1}
                </div>
                <div className="break-all font-semibold">{inp.filename}</div>
                {inp.source_id && inp.source_id !== inp.filename && (
                  <div className="mt-0.5 break-all text-xs text-muted-foreground">
                    source: {inp.source_id}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      }
    >
      {trigger}
    </HoverPopover>
  );
}

function CountLink({ href, label, children, variant = "default" }) {
  const isConflicts = variant === "conflicts";
  return (
    <Link
      href={href}
      aria-label={label}
      className={cn(
        "inline-flex items-center gap-1 rounded px-1 py-0.5 no-underline",
        isConflicts
          ? "text-warning-600 hover:bg-warning-100"
          : "text-foreground hover:bg-black/5"
      )}
    >
      {children}
    </Link>
  );
}

const FILTER_OPTIONS = [
  { value: "all", label: "All reports" },
  { value: "conflicts", label: "Has conflicts" },
  { value: "edits", label: "Has edits" },
  { value: "issues", label: "Conflicts or edits" },
];

function reportSearchText(report) {
  const parts = [
    report.aggregate_id,
    report.format,
    formatLabel(report.format),
    report.output_filename,
    formatDate(report.created_at),
  ];
  for (const inp of report.inputs || []) {
    parts.push(inp.source_id, inp.filename);
  }
  return parts.filter(Boolean).join(" ").toLowerCase();
}

function matchesFilter(report, filter) {
  const conflicts = report.counts?.conflicts ?? 0;
  const edits = report.counts?.edits ?? 0;
  if (filter === "conflicts") return conflicts > 0;
  if (filter === "edits") return edits > 0;
  if (filter === "issues") return conflicts > 0 || edits > 0;
  return true;
}

export default function DashboardPage() {
  const [state, setState] = React.useState({ status: "loading", reports: [] });
  const [search, setSearch] = React.useState("");
  const [formatFilter, setFormatFilter] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("all");

  React.useEffect(() => {
    let active = true;
    api
      .listReports()
      .then((data) => {
        if (active) setState({ status: "ready", reports: data.reports || [] });
      })
      .catch((err) => {
        if (!active) return;
        const msg = err instanceof ApiError ? err.message : "Failed to load reports";
        toast.error(msg);
        setState({ status: "error", reports: [], error: msg });
      });
    return () => {
      active = false;
    };
  }, []);

  const formatOptions = React.useMemo(() => {
    const seen = new Set(state.reports.map((r) => r.format).filter(Boolean));
    return Object.entries(FORMAT_LABELS).filter(([key]) => seen.has(key));
  }, [state.reports]);

  const filteredReports = React.useMemo(() => {
    const term = search.trim().toLowerCase();
    return state.reports.filter((r) => {
      if (formatFilter && r.format !== formatFilter) return false;
      if (!matchesFilter(r, statusFilter)) return false;
      if (!term) return true;
      return reportSearchText(r).includes(term);
    });
  }, [state.reports, search, formatFilter, statusFilter]);

  const hasFilters = search.trim() || formatFilter || statusFilter !== "all";

  return (
    <div>
      <PageHeader
        title="Merged Reports"
        actions={
          <Button asChild size="md">
            <Link href="/merge">
              <Plus className="h-4 w-4" />
              New Merge
            </Link>
          </Button>
        }
      />

      {state.status === "loading" && (
        <p className="text-muted-foreground">Loading…</p>
      )}

      {state.status === "error" && (
        <Alert variant="error">
          <AlertTitle>Could not load reports</AlertTitle>
          <AlertDescription>
            <p>{state.error}</p>
            <p className="mt-1 text-muted-foreground">
              Make sure the API service is running at the configured base URL.
            </p>
          </AlertDescription>
        </Alert>
      )}

      {state.status === "ready" && state.reports.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="mb-2">No merged reports yet.</p>
            <p className="mb-4 text-sm text-muted-foreground">
              Upload two or more FOSSology reports to create your first aggregate.
            </p>
            <Button asChild size="md">
              <Link href="/merge">Start a Merge</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {state.status === "ready" && state.reports.length > 0 && (
        <>
          <Card className="mb-4 py-4">
            <CardContent className="flex flex-wrap items-end gap-4">
              <div className="min-w-[180px] flex-1">
                <Label htmlFor="dashboard-search" className="mb-1 block">
                  Search
                </Label>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="dashboard-search"
                    placeholder="ID, format, input filename…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-8"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="dashboard-format" className="mb-1 block">
                  Format
                </Label>
                <Select
                  id="dashboard-format"
                  value={formatFilter}
                  onChange={(e) => setFormatFilter(e.target.value)}
                  className="min-w-[160px]"
                >
                  <option value="">All formats</option>
                  {formatOptions.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="dashboard-filter" className="mb-1 block">
                  Filter
                </Label>
                <Select
                  id="dashboard-filter"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="min-w-[160px]"
                >
                  {FILTER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </div>
              {hasFilters && (
                <Button
                  type="button"
                  variant="outline"
                  size="md"
                  onClick={() => {
                    setSearch("");
                    setFormatFilter("");
                    setStatusFilter("all");
                  }}
                >
                  Clear filters
                </Button>
              )}
            </CardContent>
          </Card>

          <p className="mb-2 text-xs text-muted-foreground">
            Showing {filteredReports.length} of {state.reports.length} report
            {state.reports.length === 1 ? "" : "s"}
          </p>

          {filteredReports.length === 0 ? (
            <Card>
              <CardContent className="py-6 text-center text-muted-foreground">
                No reports match your search or filters.
              </CardContent>
            </Card>
          ) : (
            <DataTable
              columns={["ID", "Format", "Created", "Inputs", "Conflicts", "Edits", ""]}
            >
              {filteredReports.map((r) => (
                <DataTableRow key={r.aggregate_id}>
                  <DataTableCell>
                    <span className="font-mono text-xs text-muted-foreground">
                      {shortId(r.aggregate_id)}
                    </span>
                  </DataTableCell>
                  <DataTableCell>
                    <Badge>{formatLabel(r.format)}</Badge>
                  </DataTableCell>
                  <DataTableCell>{formatDate(r.created_at)}</DataTableCell>
                  <DataTableCell align="center">
                    <InputsCell report={r} />
                  </DataTableCell>
                  <DataTableCell align="center">
                    <CountLink
                      href={`/reports/${r.aggregate_id}/conflicts`}
                      label={`View ${r.counts.conflicts} conflicts for report ${shortId(r.aggregate_id)}`}
                      variant="conflicts"
                    >
                      <AlertTriangle className="h-3.5 w-3.5" />
                      {r.counts.conflicts}
                    </CountLink>
                  </DataTableCell>
                  <DataTableCell align="center">
                    <CountLink
                      href={`/reports/${r.aggregate_id}/history`}
                      label={`View ${r.counts.edits} edits for report ${shortId(r.aggregate_id)}`}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      {r.counts.edits}
                    </CountLink>
                  </DataTableCell>
                  <DataTableCell>
                    <Button asChild variant="link" size="sm" className="h-auto px-0">
                      <Link href={`/reports/${r.aggregate_id}`}>View →</Link>
                    </Button>
                  </DataTableCell>
                </DataTableRow>
              ))}
            </DataTable>
          )}
        </>
      )}
    </div>
  );
}
