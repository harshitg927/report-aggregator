/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";
/**
 * VirtualizedLines — single-column virtualized text viewer.
 *
 * Renders only the visible rows using @tanstack/react-virtual.
 * Fetches line windows on demand via useWindowLoader so only the visible
 * region is ever in memory — handles 50-115 MB files safely.
 */
import * as React from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { api } from "@/lib/api";
import { useWindowLoader } from "@/lib/use-window-loader";

const LINE_HEIGHT = 20; // px — monospace line height

export function VirtualizedLines({
  id,
  source = "merged",
  totalLines,
  highlightRow = null,
  className,
}) {
  const parentRef = React.useRef(null);

  const fetchFn = React.useCallback(
    (start, count) => api.getRawLines(id, source, start, count),
    [id, source]
  );

  const { ensureWindow, getRow, reset } = useWindowLoader(fetchFn, totalLines);

  // Reset cache when the source changes.
  React.useEffect(() => { reset(); }, [source, reset]);

  const virtualizer = useVirtualizer({
    count: totalLines,
    getScrollElement: () => parentRef.current,
    estimateSize: () => LINE_HEIGHT,
    overscan: 10,
  });

  const items = virtualizer.getVirtualItems();

  // Trigger fetches for the visible + overscan range.
  React.useEffect(() => {
    if (!items.length) return;
    ensureWindow(items[0].index);
    ensureWindow(items[items.length - 1].index);
  }, [items, ensureWindow]);

  return (
    <div
      ref={parentRef}
      className={className}
      style={{ overflow: "auto", height: "60vh", contain: "strict" }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {items.map((vItem) => {
          const line = getRow(vItem.index);
          const isHighlight = vItem.index === highlightRow;
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
                alignItems: "center",
                backgroundColor: isHighlight
                  ? "var(--color-highlight, #fbbf2480)"
                  : "transparent",
              }}
            >
              {/* Line number gutter */}
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
                {vItem.index + 1}
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                  whiteSpace: "pre",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  color: line === null ? "var(--muted-foreground, #888)" : undefined,
                }}
              >
                {line === null ? "…" : line}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
