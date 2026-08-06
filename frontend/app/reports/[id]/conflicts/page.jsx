/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable, DataTableRow, DataTableCell } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";

export default function ConflictsPage() {
  const { id } = useParams();
  const [conflicts, setConflicts] = React.useState([]);
  const [status, setStatus] = React.useState("loading");

  React.useEffect(() => {
    let active = true;
    api
      .getConflicts(id)
      .then((d) => {
        if (active) {
          setConflicts(d.conflicts || []);
          setStatus("ready");
        }
      })
      .catch((err) => {
        if (!active) return;
        const msg = err instanceof ApiError ? err.message : "Failed to load conflicts";
        toast.error(msg);
        setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [id]);

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        title="Conflicts"
        actions={
          <Button asChild variant="link" size="sm" className="h-auto px-0">
            <Link href={`/reports/${id}`}>← Back to report</Link>
          </Button>
        }
      />

      {status === "loading" && (
        <p className="text-center text-muted-foreground">Loading…</p>
      )}

      {status === "ready" && conflicts.length === 0 && (
        <Card>
          <CardContent className="py-6 text-center text-muted-foreground">
            No conflicts were detected in this merge.
          </CardContent>
        </Card>
      )}

      {status === "ready" && conflicts.length > 0 && (
        <DataTable columns={["Path", "Sources / Values", "Resolution"]}>
          {conflicts.map((c, i) => (
            <DataTableRow key={`${c.path}-${i}`} className="align-top">
              <DataTableCell className="break-all font-mono text-xs">
                <AlertTriangle className="mr-1 inline h-3.5 w-3.5 text-warning-600" />
                {c.path}
              </DataTableCell>
              <DataTableCell>
                <ul className="m-0 list-none p-0">
                  {Object.entries(c.values || {}).map(([src, val]) => {
                    const chosen = val === c.chosen;
                    return (
                      <li
                        key={src}
                        className="mb-1 flex flex-wrap items-baseline gap-1.5"
                      >
                        <Badge variant="secondary" className="font-mono">
                          {src}
                        </Badge>
                        <span className="break-all">{String(val)}</span>
                        {chosen && (
                          <Badge variant="success" className="text-xs">
                            chosen
                          </Badge>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </DataTableCell>
              <DataTableCell className="text-xs text-muted-foreground">
                {c.resolution}
              </DataTableCell>
            </DataTableRow>
          ))}
        </DataTable>
      )}
    </div>
  );
}
