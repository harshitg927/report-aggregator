"""DEP5 (Debian copyright) stanza format adapter."""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter
from report_aggregator.engine.identity import compute_stanza_identity, compute_text_identity
from report_aggregator.engine.mapping import MappingConfig
from report_aggregator.engine.provenance import ConflictEntry


_HEADER_FIELDS = frozenset({"Format", "Upstream-Name", "Disclaimer", "Comment"})
_STANZA_FIELDS = frozenset({"Files", "Copyright", "License", "Comment"})


def _dep5_continuation_line(line: str) -> str:
    """Format a DEP5 continuation line, escaping leading dots per spec."""
    if not line:
        return " ."
    if line.startswith("."):
        return f" .{line}"
    return f" {line}"


def _parse_text_block(value: str, lines: list[str], start_index: int) -> tuple[str, int]:
    """Parse a <text>...</text> block that may span multiple lines."""
    if not value.startswith("<text>"):
        return value, start_index

    text_lines = [value[6:]]
    if value.rstrip().endswith("</text>"):
        text_lines[0] = text_lines[0].replace("</text>", "").strip()
        return "<text> " + text_lines[0] + " </text>", start_index

    i = start_index + 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.endswith("</text>"):
            text_lines.append(stripped.replace("</text>", "").rstrip())
            break
        text_lines.append(lines[i])
        i += 1
    return "<text> " + "\n".join(text_lines).strip() + " </text>", i


def _parse_comment_block(lines: list[str], start_index: int) -> tuple[str, int]:
    """Parse a DEP5 Comment field that may continue with `` .`` lines."""
    first = lines[start_index]
    match = re.match(r"^Comment:\s*(.*)$", first)
    if not match:
        return "", start_index

    parts = [match.group(1)]
    i = start_index + 1
    while i < len(lines):
        line = lines[i]
        if line.startswith(" .") or line == ".":
            parts.append(line[1:].strip() if line.startswith(" .") else "")
            i += 1
            continue
        break
    return "\n".join(parts).strip(), i - 1


class DEP5Adapter(FormatAdapter):
    """Adapter for FOSSology DEP5 / Debian copyright format."""

    def __init__(self, mapping: MappingConfig):
        self.mapping = mapping
        self._primary_header: dict[str, str] | None = None

    def load(self, raw: bytes) -> dict[str, Any]:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"Invalid UTF-8 in DEP5 file: {e}") from e
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")

        doc: dict[str, Any] = {"header": {}, "stanzas": [], "licenses": []}
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue

            if stripped.startswith("Files:"):
                stanza, i = self._parse_files_stanza(lines, i)
                doc["stanzas"].append(stanza)
                continue

            if stripped.startswith("License:") and not line.startswith(" "):
                license_para, i = self._parse_license_paragraph(lines, i)
                doc["licenses"].append(license_para)
                continue

            match = re.match(r"^([A-Za-z-]+):\s*(.*)$", stripped)
            if match and match.group(1) in _HEADER_FIELDS:
                key, val = match.groups()
                if key == "Comment":
                    val, i = _parse_comment_block(lines, i)
                    doc["header"][key] = val
                elif val.startswith("<text>"):
                    val, i = _parse_text_block(val, lines, i)
                    doc["header"][key] = val
                else:
                    doc["header"][key] = val
                i += 1
                continue

            i += 1

        if not doc["stanzas"] and not doc["licenses"]:
            raise ValueError(
                "Empty DEP5 report: no Files stanzas or license paragraphs found"
            )

        return doc

    def _parse_files_stanza(self, lines: list[str], start: int) -> tuple[dict[str, Any], int]:
        stanza: dict[str, Any] = {"entry_type": "files", "files": []}
        i = start

        first = lines[i]
        match = re.match(r"^Files:\s*(.*)$", first.strip())
        if match and match.group(1):
            stanza["files"].append(match.group(1).strip())
        i += 1

        while i < len(lines):
            line = lines[i]
            if line.startswith("       ") or line.startswith("\t"):
                stanza["files"].append(line.strip())
                i += 1
                continue
            if not line.strip():
                i += 1
                break

            field_match = re.match(r"^(Copyright|License|Comment):\s*(.*)$", line.strip())
            if field_match:
                key = field_match.group(1).lower()
                val = field_match.group(2)
                if key == "comment":
                    val, i = _parse_comment_block(lines, i)
                    stanza[key] = val
                else:
                    stanza[key] = val
                i += 1
                continue
            if line.strip():
                raise ValueError(
                    f"Malformed DEP5 Files stanza at line {i + 1}: unrecognized field '{line.strip()}'"
                )
            break

        return stanza, i

    def _parse_license_paragraph(
        self, lines: list[str], start: int
    ) -> tuple[dict[str, Any], int]:
        first = lines[start].strip()
        match = re.match(r"^License:\s*(.*)$", first)
        name = match.group(1).strip() if match else ""
        body_lines: list[str] = []
        i = start + 1

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                if body_lines:
                    break
                continue
            if stripped.startswith("License:") or stripped.startswith("Files:"):
                break
            if line.startswith(" ") or stripped.startswith("."):
                body_lines.append(line.lstrip())
            elif body_lines:
                break
            else:
                body_lines.append(stripped)
            i += 1

        return {
            "entry_type": "license",
            "name": name,
            "text": "\n".join(body_lines).strip(),
        }, i - 1 if body_lines and i > start + 1 else i

    def entries(self, doc: dict[str, Any]) -> Iterable[Entry]:
        if self._primary_header is None:
            self._primary_header = copy.deepcopy(doc.get("header", {}))

        for stanza in doc.get("stanzas", []):
            yield Entry(data=stanza, kind=EntryKind.STANZA, source_id="")

        for lic in doc.get("licenses", []):
            yield Entry(data=lic, kind=EntryKind.LICENSE_TEXT, source_id="")

    def identity(self, entry: Entry) -> str:
        if entry.kind == EntryKind.STANZA:
            license_expr = entry.data.get("license", "")
            files = entry.data.get("files", [])
            return compute_stanza_identity(license_expr, files)
        if entry.kind == EntryKind.LICENSE_TEXT:
            return compute_text_identity(entry.data.get("text", ""))
        return ""

    def local_refs(self, doc: dict[str, Any]) -> list[str]:
        return []

    def rewrite_refs(self, doc: dict[str, Any], remap: dict[str, str]) -> None:
        return

    def detect_conflicts(self, all_entries: list[Entry]) -> list[ConflictEntry]:
        """Flag overlapping file paths assigned to different license expressions."""
        path_to_license: dict[str, tuple[str, str]] = {}
        conflicts: list[ConflictEntry] = []

        stanzas = sorted(
            (e for e in all_entries if e.kind == EntryKind.STANZA),
            key=lambda e: e.source_id,
        )
        for entry in stanzas:
            license_expr = entry.data.get("license", "")
            for path in entry.data.get("files", []):
                path = path.strip()
                if not path:
                    continue
                existing = path_to_license.get(path)
                if existing is None:
                    path_to_license[path] = (license_expr, entry.source_id)
                elif existing[0] != license_expr:
                    first_expr, first_source = existing
                    if license_expr < first_expr or (
                        license_expr == first_expr and entry.source_id < first_source
                    ):
                        chosen = license_expr
                        values = {entry.source_id: license_expr, first_source: first_expr}
                    else:
                        chosen = first_expr
                        values = {first_source: first_expr, entry.source_id: license_expr}
                    conflicts.append(
                        ConflictEntry(
                            path=f"/dep5/glob-overlap/{path}",
                            values=values,
                            resolution="flagged",
                            chosen=chosen,
                        )
                    )
        return conflicts

    def assemble(self, entries: list[Entry], metadata: dict[str, Any]) -> dict[str, Any]:
        header = copy.deepcopy(self._primary_header or {})
        source_ids = [inp["source_id"] for inp in metadata.get("inputs", [])]
        if source_ids:
            provenance_line = f"Merged by report-aggregator from: {', '.join(source_ids)}"
            existing = header.get("Comment", "")
            header["Comment"] = f"{existing}\n .\n {provenance_line}".strip() if existing else provenance_line

        stanzas = [e.data for e in entries if e.kind == EntryKind.STANZA]
        licenses = [e.data for e in entries if e.kind == EntryKind.LICENSE_TEXT]

        return {"header": header, "stanzas": stanzas, "licenses": licenses}

    def render(self, doc: dict[str, Any]) -> bytes:
        lines: list[str] = []

        for key in ("Format", "Upstream-Name", "Disclaimer", "Comment"):
            if key not in doc.get("header", {}):
                continue
            val = doc["header"][key]
            if key == "Comment" and "\n" in val:
                lines.append(f"Comment:  {val.split(chr(10))[0]}")
                for part in val.split("\n")[1:]:
                    lines.append(_dep5_continuation_line(part))
            else:
                lines.append(f"{key}: {val}")

        if doc.get("header"):
            lines.append("")

        for stanza in doc.get("stanzas", []):
            files = stanza.get("files", [])
            if files:
                lines.append(f"Files: {files[0]}")
                for path in files[1:]:
                    lines.append(f"       {path}")
            if "copyright" in stanza:
                lines.append(f"Copyright: {stanza['copyright']}")
            if "license" in stanza:
                lines.append(f"License: {stanza['license']}")
            if "comment" in stanza:
                comment = stanza["comment"]
                if "\n" in comment:
                    parts = comment.split("\n")
                    lines.append(f"Comment: {parts[0]}")
                    for part in parts[1:]:
                        lines.append(_dep5_continuation_line(part))
                else:
                    lines.append(f"Comment: {comment}")
            lines.append("")

        for lic in doc.get("licenses", []):
            lines.append(f"License: {lic.get('name', '')}")
            text = lic.get("text", "")
            if text:
                for text_line in text.split("\n"):
                    lines.append(_dep5_continuation_line(text_line))
            lines.append("")

        output = "\n".join(lines)
        if output and not output.endswith("\n"):
            output += "\n"
        return output.encode("utf-8")
