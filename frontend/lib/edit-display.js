const MAX_PREVIEW = 120;

function previewValue(value) {
  if (value === null) return "null";
  if (value === undefined) return "—";
  const text =
    typeof value === "object" ? JSON.stringify(value) : String(value);
  if (text.length <= MAX_PREVIEW) return text;
  return `${text.slice(0, MAX_PREVIEW - 1)}…`;
}

/**
 * Split a provenance edit summary into styled segments for display.
 * @returns {{ type: "removed" | "added" | "neutral" | "arrow"; content: string }[]}
 */
export function parseSummaryLines(text) {
  if (!text || text === "—") {
    return [{ type: "neutral", content: text || "—" }];
  }

  const lines = text.split("\n");
  const hasDiffMarkers = lines.some(
    (line) =>
      (line.startsWith("-") && !line.startsWith("---")) ||
      (line.startsWith("+") && !line.startsWith("+++"))
  );

  if (!hasDiffMarkers && text.includes(" → ")) {
    const arrowIdx = text.indexOf(" → ");
    return [
      { type: "removed", content: text.slice(0, arrowIdx) },
      { type: "arrow", content: "→" },
      { type: "added", content: text.slice(arrowIdx + 3) },
    ];
  }

  return lines.map((line) => {
    if (line.startsWith("-") && !line.startsWith("---")) {
      return { type: "removed", content: line };
    }
    if (line.startsWith("+") && !line.startsWith("+++")) {
      return { type: "added", content: line };
    }
    return { type: "neutral", content: line };
  });
}

/**
 * Display text for an edit row. Prefer provenance ``summary`` when present.
 */
export function formatEditSummary(edit) {
  if (edit?.summary) return edit.summary;

  const patch = edit?.patch;
  if (!patch) return "—";

  const { op, path, value } = patch;

  if (op === "remove") return `Removed ${path || "/"}`;

  if (op === "replace" && path === "/" && typeof value === "string") {
    if (value.length > MAX_PREVIEW) {
      return `Full document updated (${value.length.toLocaleString()} characters)`;
    }
    return previewValue(value);
  }

  if (value === undefined || value === null) {
    return op === "remove" ? `Removed ${path}` : `${op} ${path}`;
  }

  return previewValue(value);
}
