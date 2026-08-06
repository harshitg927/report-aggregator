/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";

import { cn } from "@/lib/utils";
import { colorForSource } from "@/lib/colors";

export function SourceLegend({ sources = [], colors }) {
  if (!sources.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs">
      <span className="text-muted-foreground">Sources:</span>
      {sources.map((id) => {
        const c = colorForSource(colors, id);
        return (
          <span key={id} className="inline-flex items-center gap-1.5">
            <span className={cn("h-2.5 w-2.5 rounded-full", c.dot)} />
            <span className="font-mono">{id}</span>
          </span>
        );
      })}
    </div>
  );
}
