/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

/** Shared text search helpers for viewer pages. */

export function countMatches(text, term) {
  if (!term) return 0;
  const needle = term.toLowerCase();
  const haystack = text.toLowerCase();
  let count = 0;
  let pos = 0;
  while (true) {
    const idx = haystack.indexOf(needle, pos);
    if (idx === -1) break;
    count += 1;
    pos = idx + needle.length;
  }
  return count;
}

export function editMatchesSearch(edit, term) {
  if (!term.trim()) return true;
  const needle = term.toLowerCase();
  const parts = [
    edit.who,
    edit.when,
    edit.reason,
    edit.summary,
    edit.patch?.op,
    edit.patch?.path,
    edit.patch?.value != null ? String(edit.patch.value) : "",
  ];
  return parts.some((p) => p && String(p).toLowerCase().includes(needle));
}
