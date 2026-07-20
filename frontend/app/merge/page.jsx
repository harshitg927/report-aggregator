"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, RefreshCw, Search, Upload, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { FORMAT_LABELS } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { DataTable, DataTableRow, DataTableCell } from "@/components/data-table";

function uploadLabel(upload) {
  return fieldValue(upload, ["uploadName", "uploadname", "name", "filename"]) || `Upload ${uploadId(upload)}`;
}

function uploadId(upload) {
  return upload.id ?? upload.uploadId ?? upload.uploadid;
}

function fieldValue(upload, keys) {
  for (const key of keys) {
    const value = upload[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") return value;
  }
  return "";
}

function formatUploadDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function uploadHash(upload) {
  const hash = upload.hash;
  if (hash && typeof hash === "object") return hash.sha1 || hash.sha256 || hash.md5 || "";
  return fieldValue(upload, ["hash", "sha1", "uploadHash"]);
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function uploadSize(upload) {
  if (upload.hash && typeof upload.hash === "object") return formatBytes(upload.hash.size);
  return formatBytes(fieldValue(upload, ["size", "fileSize", "filesize"]));
}

function uploadDetails(upload) {
  return [
    ["ID", uploadId(upload)],
    ["Folder", fieldValue(upload, ["folderName", "foldername", "folder"])],
    ["Assignee", fieldValue(upload, ["assigneeName", "assignee_name", "assignee"])],
    ["SHA-1", uploadHash(upload)],
    ["Size", uploadSize(upload)],
  ].filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "");
}

export default function MergePage() {
  const router = useRouter();
  const [sourceMode, setSourceMode] = React.useState("local");
  const [files, setFiles] = React.useState([]);
  const [format, setFormat] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [fossologyConfig, setFossologyConfig] = React.useState(null);
  const [uploads, setUploads] = React.useState([]);
  const [uploadSearch, setUploadSearch] = React.useState("");
  const [uploadStatus, setUploadStatus] = React.useState("");
  const [selectedUploads, setSelectedUploads] = React.useState([]);
  const [fossologyFormat, setFossologyFormat] = React.useState("cyclonedx");
  const [loadingUploads, setLoadingUploads] = React.useState(false);
  const [jobMessage, setJobMessage] = React.useState("");
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    let alive = true;
    if (!api.getIntegrationsConfig) {
      setFossologyConfig({ configured: false });
      return () => {
        alive = false;
      };
    }
    api
      .getIntegrationsConfig()
      .then((body) => alive && setFossologyConfig(body.fossology || {}))
      .catch(() => alive && setFossologyConfig({ configured: false }));
    return () => {
      alive = false;
    };
  }, []);

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

  async function loadUploads() {
    setLoadingUploads(true);
    try {
      const body = await api.listFossologyUploads({
        name: uploadSearch,
        status: uploadStatus,
        limit: 50,
      });
      setUploads(Array.isArray(body.uploads) ? body.uploads : []);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load uploads";
      toast.error(msg);
    } finally {
      setLoadingUploads(false);
    }
  }

  React.useEffect(() => {
    if (sourceMode === "fossology" && fossologyConfig?.configured) loadUploads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceMode, fossologyConfig?.configured]);

  function toggleUpload(uploadId) {
    setSelectedUploads((prev) =>
      prev.includes(uploadId) ? prev.filter((id) => id !== uploadId) : [...prev, uploadId]
    );
  }

  async function pollJob(jobId) {
    while (true) {
      const job = await api.getIntegrationJob(jobId);
      setJobMessage(`${job.status} (${job.completed}/${job.total})`);
      if (job.status === "succeeded") {
        toast.success("FOSSology reports merged.");
        router.push(`/reports/${job.aggregate_id}`);
        return;
      }
      if (job.status === "failed") {
        toast.error(job.error || "FOSSology merge failed.");
        setSubmitting(false);
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  async function startFossologyMerge() {
    if (selectedUploads.length < 2) {
      toast.error("Select at least two FOSSology uploads.");
      return;
    }
    if (!fossologyFormat) {
      toast.error("Choose a report format.");
      return;
    }
    setSubmitting(true);
    setJobMessage("queued");
    try {
      const job = await api.mergeFossologyUploads({
        upload_ids: selectedUploads,
        report_format: fossologyFormat,
      });
      await pollJob(job.job_id);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to start FOSSology merge";
      toast.error(msg);
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="New Merge"
        description="Merge local report files or import reports from FOSSology uploads."
        className="text-center [&>div]:w-full [&>div]:text-center"
      />

      <div className="mb-5 flex justify-center gap-2">
        <Button
          type="button"
          variant={sourceMode === "local" ? "default" : "outline"}
          onClick={() => setSourceMode("local")}
        >
          Local files
        </Button>
        <Button
          type="button"
          variant={sourceMode === "fossology" ? "default" : "outline"}
          onClick={() => setSourceMode("fossology")}
        >
          FOSSology uploads
        </Button>
      </div>

      {sourceMode === "local" ? (
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
      ) : (
        <Card>
          <CardContent>
            {fossologyConfig && !fossologyConfig.configured ? (
              <div className="grid gap-3 text-center">
                <p className="text-sm text-muted-foreground">FOSSology is not configured.</p>
                <Button asChild className="mx-auto">
                  <Link href="/integrations">Open Integrations</Link>
                </Button>
              </div>
            ) : (
              <div className="grid gap-4">
                <div className="grid gap-3 sm:grid-cols-[1fr_150px_auto]">
                  <Input
                    value={uploadSearch}
                    onChange={(e) => setUploadSearch(e.target.value)}
                    placeholder="Search uploads"
                  />
                  <Select value={uploadStatus} onChange={(e) => setUploadStatus(e.target.value)}>
                    <option value="">Any status</option>
                    <option value="open">Open</option>
                    <option value="inprogress">In progress</option>
                    <option value="closed">Closed</option>
                    <option value="rejected">Rejected</option>
                  </Select>
                  <Button type="button" variant="outline" onClick={loadUploads} disabled={loadingUploads}>
                    {loadingUploads ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                    Search
                  </Button>
                </div>

                <DataTable columns={["", "Upload", "Status", "Uploaded"]}>
                  {uploads.map((upload) => {
                    const currentUploadId = Number(uploadId(upload));
                    const description = fieldValue(upload, [
                      "description",
                      "uploadDescription",
                      "upload_desc",
                    ]);
                    const details = uploadDetails(upload);
                    return (
                      <DataTableRow key={currentUploadId}>
                        <DataTableCell className="w-10">
                          <input
                            type="checkbox"
                            checked={selectedUploads.includes(currentUploadId)}
                            onChange={() => toggleUpload(currentUploadId)}
                            aria-label={`select ${uploadLabel(upload)}`}
                            className="h-4 w-4"
                          />
                        </DataTableCell>
                        <DataTableCell className="min-w-[260px]">
                          <div className="max-w-[38rem]">
                            <div className="font-medium text-foreground">{uploadLabel(upload)}</div>
                            {details.length > 0 && (
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                                {details.map(([label, value]) => (
                                  <span key={label}>
                                    {label}: {value}
                                  </span>
                                ))}
                              </div>
                            )}
                            {description && (
                              <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                                {description}
                              </div>
                            )}
                          </div>
                        </DataTableCell>
                        <DataTableCell className="whitespace-nowrap">
                          {fieldValue(upload, ["status", "uploadStatus", "uploadstatus"]) || "-"}
                        </DataTableCell>
                        <DataTableCell className="whitespace-nowrap">
                          {formatUploadDate(fieldValue(upload, ["uploadDate", "uploaddate", "date"]))}
                        </DataTableCell>
                      </DataTableRow>
                    );
                  })}
                  {uploads.length === 0 && (
                    <DataTableRow>
                      <DataTableCell colSpan={4} className="text-center text-muted-foreground">
                        {loadingUploads ? "Loading uploads" : "No uploads loaded"}
                      </DataTableCell>
                    </DataTableRow>
                  )}
                </DataTable>

                <div className="grid gap-3 sm:grid-cols-[220px_auto] sm:items-end">
                  <div>
                    <Label htmlFor="fossology-format" className="mb-1 block">
                      Report format
                    </Label>
                    <Select
                      id="fossology-format"
                      value={fossologyFormat}
                      onChange={(e) => setFossologyFormat(e.target.value)}
                    >
                      {Object.entries(FORMAT_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button type="button" onClick={startFossologyMerge} disabled={submitting}>
                      {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                      {submitting ? "Merging…" : "Merge Selected Uploads"}
                    </Button>
                    {jobMessage && <span className="text-sm text-muted-foreground">{jobMessage}</span>}
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
