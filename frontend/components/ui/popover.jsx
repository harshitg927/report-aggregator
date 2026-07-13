"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Minimal popover: a trigger and floating content, toggled on click and
 * dismissed on outside-click. No external dependency.
 */
function Popover({ trigger, children, contentClassName }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);

  React.useEffect(() => {
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <span className="relative inline-block" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center"
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="dialog"
          className={cn(
            "absolute z-50 mt-2 w-72 rounded-md border bg-card p-3 text-card-foreground shadow-md",
            contentClassName
          )}
        >
          {children}
        </div>
      )}
    </span>
  );
}

export { Popover };
