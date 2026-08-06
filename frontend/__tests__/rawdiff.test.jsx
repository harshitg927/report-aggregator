/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    getDiffMeta: vi.fn(),
    getDiffRows: vi.fn(),
    searchDiff: vi.fn(),
  },
}));

// Stub @tanstack/react-virtual: render all items immediately.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count, estimateSize }) => ({
    getTotalSize: () => count * (estimateSize?.() ?? 20),
    getVirtualItems: () =>
      Array.from({ length: count }, (_, i) => ({
        key: i,
        index: i,
        start: i * (estimateSize?.() ?? 20),
      })),
    measureElement: undefined,
    scrollToIndex: vi.fn(),
  }),
}));

import { api } from "@/lib/api";
import { RawDiff } from "@/components/viewer/raw-diff";

const INPUTS = [
  { input_index: 0, source_id: "zlib" },
  { input_index: 1, source_id: "fck" },
];

const MOCK_META = {
  left: "input:0",
  right: "merged",
  total_rows: 2,
  counts: { equal: 1, replace: 1, insert: 0, delete: 0 },
  left_lines: 2,
  right_lines: 2,
};

const MOCK_ROWS = {
  rows: [
    { type: "equal", left_no: 1, right_no: 1, left: "same line", right: "same line" },
    { type: "replace", left_no: 2, right_no: 2, left: "old", right: "new" },
  ],
  total_rows: 2,
};

describe("RawDiff (virtualized)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getDiffMeta.mockResolvedValue(MOCK_META);
    api.getDiffRows.mockResolvedValue(MOCK_ROWS);
    api.searchDiff.mockResolvedValue({ total: 0, truncated: false, matches: [] });
  });

  it("loads diff meta for the default source pair", async () => {
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    await waitFor(() =>
      expect(api.getDiffMeta).toHaveBeenCalledWith("agg-1", "input:0", "merged")
    );
  });

  it("renders diff rows once loaded", async () => {
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    await waitFor(() => expect(api.getDiffRows).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText("same line").length).toBeGreaterThanOrEqual(1));
    expect(screen.getAllByText("old").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("new").length).toBeGreaterThanOrEqual(1);
  });

  it("re-fetches diff meta when the right source changes", async () => {
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    await waitFor(() => expect(api.getDiffMeta).toHaveBeenCalledTimes(1));

    const rightSelect = screen.getByLabelText("diff right");
    await userEvent.selectOptions(rightSelect, "input:1");

    await waitFor(() => expect(api.getDiffMeta).toHaveBeenCalledTimes(2));
    expect(api.getDiffMeta).toHaveBeenLastCalledWith("agg-1", "input:0", "input:1");
  });

  it("shows source selectors", async () => {
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    expect(screen.getByLabelText("diff left")).toBeInTheDocument();
    expect(screen.getByLabelText("diff right")).toBeInTheDocument();
  });

  it("shows computing state while meta loads", () => {
    api.getDiffMeta.mockReturnValue(new Promise(() => {}));
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    expect(screen.getByText("Computing diff…")).toBeInTheDocument();
  });
});

describe("RawDiff search (backend-assisted)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.getDiffMeta.mockResolvedValue(MOCK_META);
    api.getDiffRows.mockResolvedValue(MOCK_ROWS);
    api.searchDiff.mockResolvedValue({
      total: 2,
      truncated: false,
      matches: [
        { row: 0, side: "left", line_no: 1 },
        { row: 1, side: "right", line_no: 2 },
      ],
    });
  });

  afterEach(() => vi.useRealTimers());

  async function typeSearch(input, value) {
    fireEvent.change(input, { target: { value } });
    await act(async () => { vi.runAllTimers(); });
  }

  it("calls searchDiff after debounce and shows match count hint", async () => {
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    await act(async () => {}); // let meta load
    const searchInput = screen.getByPlaceholderText("Find in diff…");
    await typeSearch(searchInput, "foo");
    // searchDiff should have been called (debounce fired).
    expect(api.searchDiff).toHaveBeenCalled();
    // After the promise resolves, the hint appears.
    await waitFor(() => expect(screen.getByText(/2 match/)).toBeInTheDocument());
  });

  it("shows 'No matches.' when search returns empty", async () => {
    api.searchDiff.mockResolvedValue({ total: 0, truncated: false, matches: [] });
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    await act(async () => {});
    const searchInput = screen.getByPlaceholderText("Find in diff…");
    await typeSearch(searchInput, "xyz");
    await waitFor(() => expect(screen.getByText("No matches.")).toBeInTheDocument());
  });

  it("next/prev navigate through matches and update hint cursor", async () => {
    render(<RawDiff id="agg-1" inputs={INPUTS} />);
    await act(async () => {});
    const searchInput = screen.getByPlaceholderText("Find in diff…");
    await typeSearch(searchInput, "foo");
    await waitFor(() => expect(screen.getByText(/1 of 2/)).toBeInTheDocument());

    const nextBtn = screen.getByLabelText("Next match");
    fireEvent.click(nextBtn);
    await waitFor(() => expect(screen.getByText(/2 of 2/)).toBeInTheDocument());

    fireEvent.click(nextBtn); // wraps around
    await waitFor(() => expect(screen.getByText(/1 of 2/)).toBeInTheDocument());
  });
});
