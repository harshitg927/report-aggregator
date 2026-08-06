/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";

import { cn } from "@/lib/utils";
import { formatEditSummary, parseSummaryLines } from "@/lib/edit-display";

const SEGMENT_CLASS = {
  removed:
    "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300",
  added:
    "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300",
  neutral: "text-foreground",
  arrow: "text-muted-foreground shrink-0 px-1",
};

/**
 * Renders a provenance edit summary with diff highlighting.
 */
export function EditSummary({ edit }) {
  const text = formatEditSummary(edit);
  const segments = parseSummaryLines(text);
  const isInlineArrow =
    segments.length === 3 &&
    segments[0].type === "removed" &&
    segments[1].type === "arrow" &&
    segments[2].type === "added";
  const isDiffBlock = segments.some(
    (s) => s.type === "removed" || s.type === "added"
  ) && !isInlineArrow;

  if (isInlineArrow) {
    return (
      <span
        className="inline-flex flex-wrap items-center gap-0.5 font-mono text-[9pt]"
        title={
          edit?.patch?.value != null ? String(edit.patch.value) : undefined
        }
      >
        <span className={cn("rounded px-1 py-0.5", SEGMENT_CLASS.removed)}>
          {segments[0].content}
        </span>
        <span className={SEGMENT_CLASS.arrow}>{segments[1].content}</span>
        <span className={cn("rounded px-1 py-0.5", SEGMENT_CLASS.added)}>
          {segments[2].content}
        </span>
      </span>
    );
  }

  return (
    <div
      className={cn(
        "min-w-0",
        isDiffBlock && "space-y-0.5 font-mono text-[9pt] leading-relaxed"
      )}
      title={
        edit?.patch?.value != null ? String(edit.patch.value) : undefined
      }
    >
      {segments.map((segment, i) => (
        <div
          key={i}
          className={cn(
            "whitespace-pre-wrap break-words rounded-sm px-1 py-0.5",
            SEGMENT_CLASS[segment.type]
          )}
        >
          {segment.content}
        </div>
      ))}
    </div>
  );
}
