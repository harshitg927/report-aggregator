"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Upload, X, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { FORMAT_LABELS } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { DataTable, DataTableRow, DataTableCell } from "@/components/data-table";

export default function MergePage() {
  const router = useRouter();
  const [files, setFiles] = React.useState([]);
  const [format, setFormat] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const inputRef = React.useRef(null);

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []);
    if (incoming.length === 0) return;
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size));
      const merged = [...prev];
      for (const f of incoming) {
        if (!seen.has(f.name + f.size)) merged.push(f);
      }
      return merged;
    });
  }

  function removeFile(idx) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (files.length < 2) {
      toast.error("Select at least two report files to merge.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.merge(files, format || undefined);
      toast.success("Reports merged.");
      router.push(`/reports/${result.aggregate_id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Merge failed";
      toast.error(msg);
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      <PageHeader
        title="New Merge"
        description="Upload two or more same-format FOSSology reports."
        className="text-center [&>div]:w-full [&>div]:text-center"
      />

      <form onSubmit={onSubmit}>
        <Card
          className="mb-4 cursor-pointer border-2 border-dashed border-border py-8 transition-colors hover:border-primary hover:bg-accent/30"
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            addFiles(e.dataTransfer.files);
          }}
        >
          <CardContent className="text-center">
            <Upload className="mx-auto mb-2 h-7 w-7 text-muted-foreground" />
            <p className="mb-1 font-semibold">Click to browse or drop files</p>
            <p className="text-sm text-muted-foreground">
              CycloneDX, SPDX 2/3, DEP5, ReadMeOSS, CLIXML
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              aria-label="report files"
              onChange={(e) => addFiles(e.target.files)}
            />
          </CardContent>
        </Card>

        {files.length > 0 && (
          <DataTable columns={["File", ""]} className="mb-4">
            {files.map((f, idx) => (
              <DataTableRow key={f.name + idx}>
                <DataTableCell>{f.name}</DataTableCell>
                <DataTableCell align="right" className="w-12">
                  <button
                    type="button"
                    aria-label={`remove ${f.name}`}
                    onClick={() => removeFile(idx)}
                    className="inline-flex cursor-pointer border-none bg-transparent p-0 text-alert hover:text-alert-hover"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </DataTableCell>
              </DataTableRow>
            ))}
          </DataTable>
        )}

        <div className="mb-6 text-center">
          <Label htmlFor="format" className="mb-1 block">
            Format (optional override)
          </Label>
          <Select
            id="format"
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="mx-auto min-w-[200px]"
          >
            <option value="">Auto-detect</option>
            {Object.entries(FORMAT_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex justify-center">
          <Button type="submit" disabled={submitting} size="default">
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitting ? "Merging…" : "Merge Reports"}
          </Button>
        </div>
      </form>
    </div>
  );
}
