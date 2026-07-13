import { renderHook, act, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// -------------------------------------------------------------------------- //
// useWindowLoader tests
// -------------------------------------------------------------------------- //

import { useWindowLoader } from "@/lib/use-window-loader";

describe("useWindowLoader", () => {
  it("fetches the window containing the requested row and returns its value", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      lines: ["a", "b", "c"],
    });
    const { result } = renderHook(() => useWindowLoader(fetchFn, 3));

    act(() => result.current.ensureWindow(1));
    await waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    expect(result.current.getRow(0)).toBe("a");
    expect(result.current.getRow(1)).toBe("b");
    expect(result.current.getRow(2)).toBe("c");
  });

  it("deduplicates concurrent requests for the same window", async () => {
    let resolve;
    const fetchFn = vi.fn(
      () => new Promise((r) => { resolve = r; })
    );
    const { result } = renderHook(() => useWindowLoader(fetchFn, 10));

    act(() => {
      result.current.ensureWindow(0);
      result.current.ensureWindow(0); // same window, should not trigger another fetch
    });
    act(() => resolve({ lines: Array(10).fill("x") }));
    await waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
  });

  it("reset clears the cache and allows re-fetch", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ lines: ["line1"] });
    const { result } = renderHook(() => useWindowLoader(fetchFn, 1));

    act(() => result.current.ensureWindow(0));
    await waitFor(() => expect(result.current.getRow(0)).toBe("line1"));

    act(() => result.current.reset());
    expect(result.current.getRow(0)).toBeNull();

    act(() => result.current.ensureWindow(0));
    await waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(2));
  });
});

// -------------------------------------------------------------------------- //
// VirtualizedLines tests
// -------------------------------------------------------------------------- //

vi.mock("@/lib/api", () => ({
  api: { getRawLines: vi.fn() },
}));

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));

// Minimal @tanstack/react-virtual stub that renders all items.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count, estimateSize }) => ({
    getTotalSize: () => count * estimateSize(),
    getVirtualItems: () =>
      Array.from({ length: count }, (_, i) => ({
        key: i,
        index: i,
        start: i * estimateSize(),
      })),
    measureElement: undefined,
  }),
}));

import { api } from "@/lib/api";
import { VirtualizedLines } from "@/components/viewer/virtualized-lines";

describe("VirtualizedLines", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders loaded lines", async () => {
    api.getRawLines.mockResolvedValue({ lines: ["hello", "world"], total_lines: 2 });
    render(<VirtualizedLines id="agg-1" source="merged" totalLines={2} />);
    await waitFor(() => expect(api.getRawLines).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("shows placeholder for not-yet-loaded rows", () => {
    // fetchFn never resolves in this test.
    api.getRawLines.mockReturnValue(new Promise(() => {}));
    render(<VirtualizedLines id="agg-1" source="merged" totalLines={5} />);
    // All 5 rows should render as placeholders (…).
    const placeholders = screen.getAllByText("…");
    expect(placeholders.length).toBe(5);
  });
});
