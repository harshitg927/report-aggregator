/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "agg-1" }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: { getEdits: vi.fn(), undoEdit: vi.fn(), getConflicts: vi.fn() },
}));

import { api } from "@/lib/api";
import HistoryPage from "@/app/reports/[id]/history/page";
import ConflictsPage from "@/app/reports/[id]/conflicts/page";

describe("history page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.confirm = vi.fn(() => true);
  });

  it("lists edits and undoes one", async () => {
    api.getEdits
      .mockResolvedValueOnce({
        edits: [
          {
            who: "alice@example.com",
            when: "2026-06-22T00:00:00Z",
            patch: { op: "replace", path: "/components/0/name", value: "x" },
            reason: "fix name",
            summary: "old-name → x",
          },
        ],
      })
      .mockResolvedValue({ edits: [] });
    api.undoEdit.mockResolvedValue({ ok: true });

    render(<HistoryPage />);
    await waitFor(() =>
      expect(screen.getByText("alice@example.com")).toBeInTheDocument()
    );
    expect(screen.getByText("/components/0/name")).toBeInTheDocument();
    expect(screen.getByText("old-name")).toBeInTheDocument();
    expect(screen.getByText("x")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /undo/i }));
    await waitFor(() => expect(api.undoEdit).toHaveBeenCalledWith("agg-1", 1));
    await waitFor(() =>
      expect(screen.getByText(/No edits have been applied/i)).toBeInTheDocument()
    );
  });

  it("filters edits by search text", async () => {
    api.getEdits.mockResolvedValue({
      edits: [
        {
          who: "alice@example.com",
          when: "2026-06-22T00:00:00Z",
          patch: { op: "replace", path: "/a", value: "x" },
          summary: "old → x",
        },
        {
          who: "bob@example.com",
          when: "2026-06-23T00:00:00Z",
          patch: { op: "replace", path: "/b", value: "y" },
          summary: "other change",
        },
      ],
    });

    render(<HistoryPage />);
    await waitFor(() =>
      expect(screen.getByText("alice@example.com")).toBeInTheDocument()
    );

    await userEvent.type(screen.getByLabelText(/search who/i), "bob");
    expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument();
    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
  });
});

describe("conflicts page", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders conflicts with per-source values and chosen marker", async () => {
    api.getConflicts.mockResolvedValue({
      conflicts: [
        {
          path: "/file/abc/copyright",
          values: { zlib: "Copyright X", fck: "Copyright Y" },
          resolution: "first-writer",
          chosen: "Copyright X",
        },
      ],
    });

    render(<ConflictsPage />);
    await waitFor(() =>
      expect(screen.getByText("/file/abc/copyright")).toBeInTheDocument()
    );
    expect(screen.getByText("Copyright Y")).toBeInTheDocument();
    expect(screen.getByText("chosen")).toBeInTheDocument();
    expect(screen.getByText(/first-writer/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no conflicts", async () => {
    api.getConflicts.mockResolvedValue({ conflicts: [] });
    render(<ConflictsPage />);
    await waitFor(() =>
      expect(screen.getByText(/No conflicts were detected/i)).toBeInTheDocument()
    );
  });
});
