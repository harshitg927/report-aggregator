import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "agg-1" }),
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    getReport: vi.fn(),
    getFields: vi.fn(),
    getEdits: vi.fn(),
    applyEdit: vi.fn(),
    downloadUrl: (id) => `http://api/api/reports/${id}/download`,
  },
}));

import { api } from "@/lib/api";
import ReportViewerPage from "@/app/reports/[id]/page";

const TREE = {
  sources: ["zlib", "fck"],
  truncated: false,
  nodes: [
    {
      path: "/components/0/name",
      key: "name",
      value: "zlib",
      valueType: "str",
      isLeaf: true,
      depth: 2,
      sources: ["zlib"],
      conflict: null,
    },
    {
      path: "/components/0/copyright",
      key: "copyright",
      value: "Copyright X",
      valueType: "str",
      isLeaf: true,
      depth: 2,
      sources: ["zlib", "fck"],
      conflict: {
        path: "/file/abc/copyright",
        values: { zlib: "Copyright X", fck: "Copyright Y" },
        resolution: "first-writer",
        chosen: "Copyright X",
      },
    },
  ],
};

describe("report viewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getReport.mockResolvedValue({
      aggregate_id: "agg-1",
      format: "cyclonedx",
      counts: { inputs: 2, conflicts: 1, edits: 0 },
    });
    api.getFields.mockResolvedValue(TREE);
    api.getEdits.mockResolvedValue({ edits: [] });
  });

  it("renders provenance legend, fields and a conflict badge", async () => {
    render(<ReportViewerPage />);
    await waitFor(() => expect(screen.getByText("Merged Report")).toBeInTheDocument());

    // Source legend lists both inputs.
    expect(screen.getAllByText("zlib").length).toBeGreaterThan(0);
    expect(screen.getAllByText("fck").length).toBeGreaterThan(0);

    // Conflict badge present.
    expect(screen.getByText("conflict")).toBeInTheDocument();
  });

  it("filters to conflicts only", async () => {
    render(<ReportViewerPage />);
    await waitFor(() => expect(screen.getByText("Merged Report")).toBeInTheDocument());

    expect(screen.getByText("name")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("filter"), "conflicts");

    await waitFor(() => expect(screen.queryByText("name")).not.toBeInTheDocument());
    expect(screen.getByText("copyright")).toBeInTheDocument();
  });

  it("reveals conflict values in a popover", async () => {
    render(<ReportViewerPage />);
    await waitFor(() => expect(screen.getByText("Merged Report")).toBeInTheDocument());

    await userEvent.click(screen.getByText("conflict"));
    expect(screen.getByText("Conflicting values")).toBeInTheDocument();
    expect(screen.getByText("Copyright Y")).toBeInTheDocument();
  });

  it("applies an inline edit and posts the RFC-6902 patch", async () => {
    api.applyEdit.mockResolvedValue({ ok: true });
    // After save the viewer reloads; return updated tree + one edit.
    const editedTree = {
      ...TREE,
      nodes: TREE.nodes.map((n) =>
        n.path === "/components/0/name" ? { ...n, value: "zlib-edited" } : n
      ),
    };
    api.getFields.mockResolvedValueOnce(TREE).mockResolvedValue(editedTree);
    api.getEdits
      .mockResolvedValueOnce({ edits: [] })
      .mockResolvedValue({ edits: [{ patch: { path: "/components/0/name" } }] });

    render(<ReportViewerPage />);
    await waitFor(() => expect(screen.getByText("Merged Report")).toBeInTheDocument());

    // Open the edit dialog via the row's edit button.
    await userEvent.click(screen.getByLabelText("edit /components/0/name"));
    const valueInput = await screen.findByLabelText("Value");
    await userEvent.clear(valueInput);
    await userEvent.type(valueInput, "zlib-edited");
    await userEvent.click(screen.getByRole("button", { name: /save edit/i }));

    await waitFor(() => expect(api.applyEdit).toHaveBeenCalledTimes(1));
    const [, payload] = api.applyEdit.mock.calls[0];
    expect(payload).toMatchObject({
      op: "replace",
      path: "/components/0/name",
      value: "zlib-edited",
    });
    await waitFor(() =>
      expect(screen.getByText("zlib-edited")).toBeInTheDocument()
    );
  });
});
