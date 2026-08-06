/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";
/**
 * VirtualizedFieldTree — windowed rendering for large field trees.
 *
 * Renders only visible FieldRow components so 10k+ nodes stay scrollable.
 */
import * as React from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { FieldRow } from "@/components/viewer/field-row";

const ROW_HEIGHT = 28;

export function VirtualizedFieldTree({ nodes, colors, editedPaths, onEdit }) {
  const parentRef = React.useRef(null);

  const virtualizer = useVirtualizer({
    count: nodes.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 15,
  });

  const items = virtualizer.getVirtualItems();

  if (nodes.length === 0) {
    return null;
  }

  // Fallback when the scroll container has no measurable size (e.g. jsdom tests).
  if (items.length === 0) {
    return (
      <div ref={parentRef} style={{ maxHeight: "65vh", overflowY: "auto" }}>
        {nodes.map((node) => (
          <FieldRow
            key={node.path}
            node={node}
            colors={colors}
            edited={editedPaths.has(node.path)}
            onEdit={onEdit}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      style={{ maxHeight: "65vh", overflowY: "auto" }}
    >
      <div
        style={{
          height: virtualizer.getTotalSize(),
          position: "relative",
          width: "100%",
        }}
      >
        {items.map((vItem) => {
          const node = nodes[vItem.index];
          return (
            <div
              key={node.path}
              data-index={vItem.index}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${vItem.start}px)`,
                height: ROW_HEIGHT,
                overflow: "hidden",
              }}
            >
              <FieldRow
                node={node}
                colors={colors}
                edited={editedPaths.has(node.path)}
                onEdit={onEdit}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
