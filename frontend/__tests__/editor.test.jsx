import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Stub the dynamically-imported CodeMirror with a controlled textarea.
vi.mock("next/dynamic", () => ({
  default: () => (props) => (
    <textarea
      aria-label="document editor"
      value={props.value}
      onChange={(e) => props.onChange?.(e.target.value)}
    />
  ),
}));

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));

const toastError = vi.fn();
const toastSuccess = vi.fn();
const toastInfo = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: (...a) => toastError(...a),
    success: (...a) => toastSuccess(...a),
    info: (...a) => toastInfo(...a),
  },
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    getRawMeta: vi.fn(),
    getRaw: vi.fn(),
    saveDocument: vi.fn(),
    downloadUrl: (id) => `/api/reports/${id}/download`,
  },
}));

import { api } from "@/lib/api";
import { DocumentEditor } from "@/components/viewer/document-editor";

const SMALL_META = { size: 1024, total_lines: 10 };
// 10 MB — above the default 2 MB highlight threshold
const LARGE_META = { size: 10_000_000, total_lines: 200_000 };

describe("document editor — small file (editable with highlighting)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getRawMeta.mockResolvedValue(SMALL_META);
    api.getRaw.mockResolvedValue('{"a": 1}');
  });

  it("loads the raw document and saves edits", async () => {
    api.saveDocument.mockResolvedValue({ ok: true, changes: 1 });
    const onSaved = vi.fn();

    render(<DocumentEditor id="agg-1" format="cyclonedx" onSaved={onSaved} />);

    const editor = await screen.findByLabelText("document editor");
    expect(editor).toHaveValue('{"a": 1}');

    // Save is disabled until the document changes.
    const saveBtn = screen.getByRole("button", { name: /save/i });
    expect(saveBtn).toBeDisabled();

    fireEvent.change(editor, { target: { value: '{"a": 2}' } });
    expect(saveBtn).not.toBeDisabled();

    await userEvent.click(saveBtn);
    await waitFor(() => expect(api.saveDocument).toHaveBeenCalledTimes(1));
    const [, payload] = api.saveDocument.mock.calls[0];
    expect(payload.content).toBe('{"a": 2}');
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("surfaces a validation error from the API", async () => {
    api.saveDocument.mockRejectedValue(new Error("Invalid document"));
    render(<DocumentEditor id="agg-1" format="cyclonedx" />);

    const editor = await screen.findByLabelText("document editor");
    fireEvent.change(editor, { target: { value: "not json" } });
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });

  it("does not show the large-file notice for small files", async () => {
    render(<DocumentEditor id="agg-1" format="cyclonedx" />);
    await screen.findByLabelText("document editor");
    expect(screen.queryByText(/syntax highlighting is off/i)).not.toBeInTheDocument();
  });
});

describe("document editor — large file (always editable, plain-text mode)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getRawMeta.mockResolvedValue(LARGE_META);
    api.getRaw.mockResolvedValue("line1\nline2\nline3");
  });

  it("renders the editor (not read-only) for large files", async () => {
    render(<DocumentEditor id="agg-1" format="cyclonedx" />);
    const editor = await screen.findByLabelText("document editor");
    expect(editor).toBeInTheDocument();
    // Not disabled — fully editable
    expect(editor).not.toBeDisabled();
  });

  it("shows the large-file plain-text notice", async () => {
    render(<DocumentEditor id="agg-1" format="cyclonedx" />);
    await waitFor(() =>
      expect(screen.getByText(/syntax highlighting is off/i)).toBeInTheDocument()
    );
  });

  it("shows the save button and enables it after editing", async () => {
    render(<DocumentEditor id="agg-1" format="cyclonedx" />);
    const editor = await screen.findByLabelText("document editor");
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
    fireEvent.change(editor, { target: { value: "changed content" } });
    expect(screen.getByRole("button", { name: /save/i })).not.toBeDisabled();
  });

  it("saves large-file edits via saveDocument", async () => {
    api.saveDocument.mockResolvedValue({ ok: true, changes: 3 });
    const onSaved = vi.fn();
    render(<DocumentEditor id="agg-1" format="cyclonedx" onSaved={onSaved} />);

    const editor = await screen.findByLabelText("document editor");
    fireEvent.change(editor, { target: { value: "large edited content" } });
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(api.saveDocument).toHaveBeenCalledTimes(1));
    const [, payload] = api.saveDocument.mock.calls[0];
    expect(payload.content).toBe("large edited content");
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
