/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";
/**
 * useWindowLoader — on-demand window fetcher for the virtualized viewers.
 *
 * Maintains a sparse cache of fetched rows keyed by window index.
 * The virtualizer calls `ensureWindow(rowIndex)` as rows come into view;
 * inflight deduplication prevents duplicate requests for the same window.
 */
import * as React from "react";

const WINDOW_SIZE = 200;
const OVERSCAN = 20;

/**
 * @param {Function} fetchFn  (start, count) => Promise<{rows|lines, total_lines|total_rows}>
 * @param {number}   total    Total rows/lines (known from meta, or 0 until loaded)
 */
export function useWindowLoader(fetchFn, total) {
  // windowIndex → array of row/line objects (or null placeholders)
  const cache = React.useRef({});
  // windowIndex → true while in-flight
  const inflight = React.useRef({});
  const [, rerender] = React.useReducer((n) => n + 1, 0);

  const getWindow = React.useCallback((rowIndex) => {
    return Math.floor(rowIndex / WINDOW_SIZE);
  }, []);

  const ensureWindow = React.useCallback(
    (rowIndex) => {
      const lo = Math.max(0, rowIndex - OVERSCAN);
      const hi = Math.min(total - 1, rowIndex + WINDOW_SIZE + OVERSCAN);
      for (let r = lo; r <= hi; r += WINDOW_SIZE) {
        const wi = getWindow(r);
        if (cache.current[wi] !== undefined || inflight.current[wi]) continue;
        inflight.current[wi] = true;
        const start = wi * WINDOW_SIZE;
        fetchFn(start, WINDOW_SIZE)
          .then((data) => {
            const items = data.rows ?? data.lines;
            cache.current[wi] = items;
            rerender();
          })
          .catch(() => {
            cache.current[wi] = [];
          })
          .finally(() => {
            delete inflight.current[wi];
          });
      }
    },
    [fetchFn, total, getWindow]
  );

  const getRow = React.useCallback(
    (rowIndex) => {
      const wi = getWindow(rowIndex);
      const window = cache.current[wi];
      if (!window) return null; // not yet loaded
      return window[rowIndex - wi * WINDOW_SIZE] ?? null;
    },
    [getWindow]
  );

  const reset = React.useCallback(() => {
    cache.current = {};
    inflight.current = {};
    rerender();
  }, []);

  return { ensureWindow, getRow, reset };
}
