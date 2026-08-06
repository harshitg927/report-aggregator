/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";
/**
 * VirtualizedDiff — two-column split diff viewer using windowed rendering.
 *
 * Both columns share the same virtualizer and scroll container so they stay
 * perfectly aligned. Line content is fetched on demand via useWindowLoader
 * and the getDiffRows API. Works safely with 50-115 MB files.
 */
import * as React from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { api } from "@/lib/api";
import { useWindowLoader } from "@/lib/use-window-loader";

const LINE_HEIGHT = 20; // px

// Change type → background color tokens (CSS variables for light/dark)
const ROW_BG = {
  equal: "transparent",
  replace: "var(--diff-replace, #fef3c780)",
  insert: "var(--diff-insert, #d1fae580)",
  delete: "var(--diff-delete, #fee2e280)",
};

function LineCell({ text, lineNo, bg }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        height: LINE_HEIGHT,
        backgroundColor: bg,
        overflow: "hidden",
        flex: 1,
        minWidth: 0,
      }}
    >
      <span
        style={{
          display: "inline-block",
          width: "4em",
          flexShrink: 0,
          textAlign: "right",
          paddingRight: "0.75em",
          color: "var(--muted-foreground, #888)",
          userSelect: "none",
          fontFamily: "monospace",
          fontSize: "0.75rem",
        }}
      >
        {lineNo ?? ""}
      </span>
      <span
        style={{
          fontFamily: "monospace",
          fontSize: "0.75rem",
          whiteSpace: "pre",
          overflow: "hidden",
          textOverflow: "ellipsis",
          color: text === null ? "var(--muted-foreground, #888)" : undefined,
        }}
      >
        {text === null ? "…" : (text ?? "")}
      </span>
    </div>
  );
}

export function VirtualizedDiff({
  id,
  left,
  right,
  totalRows,
  highlightRow = null,
  className,
}) {
  const parentRef = React.useRef(null);

  const fetchFn = React.useCallback(
    (start, count) => api.getDiffRows(id, left, right, start, count),
    [id, left, right]
  );

  const { ensureWindow, getRow, reset } = useWindowLoader(fetchFn, totalRows);

  React.useEffect(() => { reset(); }, [left, right, reset]);

  const virtualizer = useVirtualizer({
    count: totalRows,
    getScrollElement: () => parentRef.current,
    estimateSize: () => LINE_HEIGHT,
    overscan: 10,
  });

  const items = virtualizer.getVirtualItems();

  React.useEffect(() => {
    if (!items.length) return;
    ensureWindow(items[0].index);
    ensureWindow(items[items.length - 1].index);
  }, [items, ensureWindow]);

  // Scroll to highlight row when it changes.
  React.useEffect(() => {
    if (highlightRow !== null) {
      virtualizer.scrollToIndex(highlightRow, { align: "center" });
    }
  }, [highlightRow]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      ref={parentRef}
      className={className}
      style={{ overflow: "auto", height: "60vh", contain: "strict" }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {items.map((vItem) => {
          const row = getRow(vItem.index);
          const type = row?.type ?? "equal";
          const bg = vItem.index === highlightRow
            ? "var(--color-highlight, #fbbf2480)"
            : ROW_BG[type] ?? "transparent";

          return (
            <div
              key={vItem.key}
              data-index={vItem.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: vItem.start,
                left: 0,
                right: 0,
                height: LINE_HEIGHT,
                display: "flex",
              }}
            >
              <LineCell
                text={row ? row.left : null}
                lineNo={row?.left_no}
                bg={type === "insert" ? "var(--diff-insert-absent, #f0fdf480)" : bg}
              />
              {/* Divider */}
              <div style={{ width: 1, flexShrink: 0, background: "var(--border, #e2e8f0)" }} />
              <LineCell
                text={row ? row.right : null}
                lineNo={row?.right_no}
                bg={type === "delete" ? "var(--diff-delete-absent, #fff1f280)" : bg}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
