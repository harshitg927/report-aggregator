// API client for the report-aggregator FastAPI service.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8080";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch {
      // ignore JSON parse errors
    }
    throw new ApiError(detail, res.status);
  }
  return res;
}

async function json(path, options) {
  const res = await request(path, options);
  return res.json();
}

async function text(path, options) {
  const res = await request(path, options);
  return res.text();
}

export const api = {
  health: () => json("/api/health"),

  listReports: () => json("/api/reports"),

  getReport: (id) => json(`/api/reports/${id}`),

  merge: async (files, format) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    if (format) form.append("format", format);
    // Let the browser set the multipart boundary.
    const res = await fetch(`${API_BASE_URL}/api/merge`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      let detail = `Merge failed (${res.status})`;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
      } catch {
        // ignore
      }
      throw new ApiError(detail, res.status);
    }
    return res.json();
  },

  getFields: (id) => json(`/api/reports/${id}/fields`),

  getRaw: (id) => text(`/api/reports/${id}/raw`),

  getInputRaw: (id, idx) => text(`/api/reports/${id}/inputs/${idx}/raw`),

  getConflicts: (id) => json(`/api/reports/${id}/conflicts`),

  getEdits: (id) => json(`/api/reports/${id}/edits`),

  applyEdit: (id, edit) =>
    json(`/api/reports/${id}/edits`, {
      method: "POST",
      body: JSON.stringify(edit),
    }),

  undoEdit: (id, index) =>
    json(`/api/reports/${id}/edits/${index}`, { method: "DELETE" }),

  saveDocument: (id, payload) =>
    json(`/api/reports/${id}/document`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  // Direct download URLs (used as anchor hrefs so the browser handles the file).
  downloadUrl: (id) => `${API_BASE_URL}/api/reports/${id}/download`,
  provenanceDownloadUrl: (id) =>
    `${API_BASE_URL}/api/reports/${id}/provenance/download`,

  // Large-file-safe windowed raw/diff endpoints.
  getRawMeta: (id, source = "merged") =>
    json(`/api/reports/${id}/raw/meta?source=${encodeURIComponent(source)}`),

  getRawLines: (id, source = "merged", start = 0, count = 200) =>
    json(`/api/reports/${id}/raw/lines?source=${encodeURIComponent(source)}&start=${start}&count=${count}`),

  getDiffMeta: (id, left, right) =>
    json(`/api/reports/${id}/diff/meta?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`),

  getDiffRows: (id, left, right, start = 0, count = 200) =>
    json(`/api/reports/${id}/diff/rows?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}&start=${start}&count=${count}`),

  searchDiff: (id, left, right, q, caseSensitive = false, limit = 500) =>
    json(`/api/reports/${id}/diff/search?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}&q=${encodeURIComponent(q)}&case_sensitive=${caseSensitive}&limit=${limit}`),
};
