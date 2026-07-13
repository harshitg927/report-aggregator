"use client";

import * as React from "react";
import { AlertTriangle, Pencil } from "lucide-react";
import { cn } from "@/lib/utils";
import { colorForSource } from "@/lib/colors";
import { Popover } from "@/components/ui/popover";

function valuePreview(value, type) {
  if (type === "null") return "null";
  if (type === "bool") return String(value);
  if (typeof value === "string") return value;
  return String(value);
}

function SourceBadges({ sources, colors }) {
  if (!sources || sources.length === 0) return null;
  return (
    <span className="flex shrink-0 items-center gap-1">
      {sources.map((id) => {
        const c = colorForSource(colors, id);
        return (
          <span
            key={id}
            title={id}
            className={cn(
              "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium",
              c.bg,
              c.text
            )}
          >
            {id}
          </span>
        );
      })}
    </span>
  );
}

function ConflictPopover({ conflict, colors }) {
  return (
    <Popover
      trigger={
        <span className="inline-flex items-center gap-1 rounded bg-warning-100 px-1.5 py-0.5 text-[10px] font-medium text-warning-600">
          <AlertTriangle className="h-3 w-3" />
          conflict
        </span>
      }
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold">Conflicting values</p>
        <ul className="space-y-1">
          {Object.entries(conflict.values || {}).map(([src, val]) => {
            const c = colorForSource(colors, src);
            return (
              <li key={src} className="text-xs">
                <span className={cn("mr-1 rounded px-1 py-0.5 font-mono", c.bg, c.text)}>
                  {src}
                </span>
                <span className="break-all">{String(val)}</span>
              </li>
            );
          })}
        </ul>
        <p className="text-xs text-muted-foreground">
          Resolution: {conflict.resolution} → chosen{" "}
          <span className="break-all font-medium">{String(conflict.chosen)}</span>
        </p>
      </div>
    </Popover>
  );
}

export function FieldRow({ node, colors, edited, onEdit }) {
  const indent = { paddingLeft: `${node.depth * 16 + 8}px` };
  const isEditableLeaf = node.isLeaf && typeof onEdit === "function";

  return (
    <div
      className={cn(
        "group flex items-start gap-2 border-b px-2 py-1.5 text-sm",
        node.conflict && "bg-warning-100/50"
      )}
      style={indent}
    >
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-mono text-xs text-muted-foreground">{node.key}</span>

        {node.isLeaf ? (
          <span
            className={cn(
              "break-all font-medium",
              isEditableLeaf &&
                "cursor-pointer rounded px-1 hover:bg-accent hover:ring-1 hover:ring-ring"
            )}
            onClick={isEditableLeaf ? () => onEdit(node) : undefined}
            title={isEditableLeaf ? "Click to edit" : undefined}
          >
            {valuePreview(node.value, node.valueType)}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">
            {node.valueType}
            {typeof node.childCount === "number" ? ` · ${node.childCount}` : ""}
          </span>
        )}

        {edited && (
          <span className="inline-flex items-center gap-1 rounded bg-tertiary1-200 px-1.5 py-0.5 text-[10px] font-medium text-tertiary1-900">
            <Pencil className="h-3 w-3" />
            edited
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {node.conflict && <ConflictPopover conflict={node.conflict} colors={colors} />}
        <SourceBadges sources={node.sources} colors={colors} />
        {isEditableLeaf && (
          <button
            type="button"
            aria-label={`edit ${node.path}`}
            onClick={() => onEdit(node)}
            className="opacity-0 transition-opacity group-hover:opacity-100"
          >
            <Pencil className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
          </button>
        )}
      </div>
    </div>
  );
}
