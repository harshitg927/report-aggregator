/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

const CLOSE_DELAY_MS = 120;

/**
 * Tooltip-style popover shown on hover and keyboard focus.
 * Renders via portal with fixed positioning so it is not clipped by table overflow.
 */
export function HoverPopover({
  children,
  content,
  className,
  contentClassName,
  width = "18rem",
  maxHeight = "16rem",
}) {
  const [open, setOpen] = React.useState(false);
  const [position, setPosition] = React.useState({ top: 0, left: 0 });
  const triggerRef = React.useRef(null);
  const popoverRef = React.useRef(null);
  const closeTimerRef = React.useRef(null);

  const parsedWidth =
    typeof width === "number" ? width : parseFloat(width) * (width.endsWith("rem") ? 16 : 1);

  const parsedMaxHeight =
    typeof maxHeight === "number"
      ? maxHeight
      : parseFloat(maxHeight) * (maxHeight.endsWith("rem") ? 16 : 1);

  const updatePosition = React.useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const popoverWidth = Number.isFinite(parsedWidth) ? parsedWidth : 288;
    const popoverMaxHeight = Number.isFinite(parsedMaxHeight) ? parsedMaxHeight : 256;

    let left = rect.left + rect.width / 2 - popoverWidth / 2;
    let top = rect.bottom + 6;

    left = Math.max(8, Math.min(left, window.innerWidth - popoverWidth - 8));

    if (top + popoverMaxHeight > window.innerHeight - 8) {
      top = rect.top - popoverMaxHeight - 6;
    }
    top = Math.max(8, top);

    setPosition({ top, left });
  }, [parsedWidth, parsedMaxHeight]);

  const cancelClose = React.useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const scheduleClose = React.useCallback(() => {
    cancelClose();
    closeTimerRef.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }, [cancelClose]);

  const handleOpen = React.useCallback(() => {
    cancelClose();
    updatePosition();
    setOpen(true);
  }, [cancelClose, updatePosition]);

  React.useEffect(() => {
    if (!open) return undefined;

    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);

    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, updatePosition]);

  React.useEffect(() => () => cancelClose(), [cancelClose]);

  const popover =
    open && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={popoverRef}
            role="tooltip"
            style={{
              position: "fixed",
              top: position.top,
              left: position.left,
              width: typeof width === "number" ? `${width}px` : width,
              maxHeight: typeof maxHeight === "number" ? `${maxHeight}px` : maxHeight,
            }}
            className={cn(
              "z-[200] flex flex-col overflow-hidden rounded-md border border-border bg-card text-card-foreground shadow-lg",
              contentClassName
            )}
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
          >
            <div className="min-h-0 flex-1 overflow-y-auto p-3">{content}</div>
          </div>,
          document.body
        )
      : null;

  return (
    <>
      <span
        ref={triggerRef}
        className={cn("inline-block", className)}
        onMouseEnter={handleOpen}
        onMouseLeave={scheduleClose}
        onFocus={handleOpen}
        onBlur={(e) => {
          const next = e.relatedTarget;
          if (
            !triggerRef.current?.contains(next) &&
            !popoverRef.current?.contains(next)
          ) {
            setOpen(false);
          }
        }}
      >
        {children}
      </span>
      {popover}
    </>
  );
}
