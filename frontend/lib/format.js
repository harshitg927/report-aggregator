/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

export const FORMAT_LABELS = {
  cyclonedx: "CycloneDX 1.4",
  spdx2tv: "SPDX 2 TV",
  dep5: "DEP5",
  readmeoss: "ReadMeOSS",
  spdx3json: "SPDX 3 JSON",
  clixml: "CLIXML",
};

export function formatLabel(fmt) {
  return FORMAT_LABELS[fmt] || fmt;
}

export function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function shortId(id) {
  if (!id) return "";
  return id.length > 8 ? id.slice(0, 8) : id;
}
