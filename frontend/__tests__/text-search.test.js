/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

import { describe, it, expect } from "vitest";
import { countMatches, editMatchesSearch } from "@/lib/text-search";

describe("text-search helpers", () => {
  it("counts non-overlapping matches", () => {
    expect(countMatches("foo bar foo", "foo")).toBe(2);
    expect(countMatches("hello", "xyz")).toBe(0);
  });

  it("matches edits by summary and metadata", () => {
    const edit = {
      who: "alice@test.com",
      summary: "OLD → NEW",
      patch: { op: "replace", path: "/x" },
    };
    expect(editMatchesSearch(edit, "alice")).toBe(true);
    expect(editMatchesSearch(edit, "NEW")).toBe(true);
    expect(editMatchesSearch(edit, "missing")).toBe(false);
  });
});
