/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

// Stable color assignment for provenance source ids.

const PALETTE = [
  { bg: "bg-info-100", text: "text-info-500", dot: "bg-info-500" },
  { bg: "bg-success-100", text: "text-success-500", dot: "bg-success-500" },
  { bg: "bg-warning-100", text: "text-warning-600", dot: "bg-warning-500" },
  { bg: "bg-tertiary2-200", text: "text-tertiary2-900", dot: "bg-tertiary2-800" },
  { bg: "bg-brand-100", text: "text-brand-900", dot: "bg-brand-800" },
  { bg: "bg-tertiary1-200", text: "text-tertiary1-900", dot: "bg-tertiary1-800" },
  { bg: "bg-neutral-200", text: "text-neutral-800", dot: "bg-neutral-700" },
  { bg: "bg-error-100", text: "text-error-500", dot: "bg-error-500" },
];

/**
 * Build a stable map from source id -> palette entry, ordered by the provided
 * list of source ids so colors are consistent across a report.
 */
export function buildSourceColors(sourceIds = []) {
  const map = {};
  sourceIds.forEach((id, i) => {
    map[id] = PALETTE[i % PALETTE.length];
  });
  return map;
}

export function colorForSource(map, id) {
  return (
    map[id] || {
      bg: "bg-muted",
      text: "text-muted-foreground",
      dot: "bg-muted-foreground",
    }
  );
}
