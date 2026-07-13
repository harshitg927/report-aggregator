"use client";

import * as React from "react";
import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

/**
 * Search bar for in-document or list filtering.
 */
export function TextSearchBar({
  value,
  onChange,
  placeholder = "Search…",
  id = "text-search",
  hint,
  onNext,
  onPrev,
  showNav = false,
  className,
}) {
  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search
            className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            id={id}
            aria-label={placeholder}
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="pl-8"
            onKeyDown={(e) => {
              if (e.key === "Enter" && showNav && onNext) {
                e.preventDefault();
                onNext();
              }
            }}
          />
        </div>
        {value && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Clear search"
            onClick={() => onChange("")}
            className="h-9 px-2"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
        {showNav && value && (
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Previous match"
              onClick={onPrev}
              className="h-9 px-2"
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Next match"
              onClick={onNext}
              className="h-9 px-2"
            >
              <ChevronDown className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
      {hint && (
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}
