"""ReadMeOSS NOTICE-style text format adapter."""

from __future__ import annotations

import copy
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter
from report_aggregator.engine.identity import compute_text_identity, normalize_readmeoss_text
from report_aggregator.engine.mapping import MappingConfig

_MAJOR_SEP = "=" * 120
_MINOR_SEP = "-" * 120
_SECTION_NAMES = ("MAIN LICENSES", "OTHER LICENSES", "ACKNOWLEDGEMENTS")


def _is_major_separator(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 20 and set(stripped) == {"="}


def _is_minor_separator(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 20 and set(stripped) == {"-"}


def _is_footer_marker(line: str) -> bool:
    stripped = line.strip()
    return stripped in ("<Copyright notices>", "<notices>")


class ReadMeOSSAdapter(FormatAdapter):
    """Adapter for FOSSology ReadMeOSS text format."""

    def __init__(self, mapping: MappingConfig):
        self.mapping = mapping
        self._primary_doc: dict[str, Any] | None = None

    def _parse_footer(self, lines: list[str], start: int) -> tuple[dict[str, str], int]:
        footer = {"copyright_notices": "<Copyright notices>", "notices": "<notices>"}
        i = start
        if i < len(lines) and _is_minor_separator(lines[i]):
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines) and _is_footer_marker(lines[i]):
            footer["copyright_notices"] = lines[i].strip()
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines) and _is_footer_marker(lines[i]):
            footer["notices"] = lines[i].strip()
            i += 1
        return footer, i

    def load(self, raw: bytes) -> dict[str, Any]:
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")

        doc: dict[str, Any] = {
            "header": {"package_name": ""},
            "sections": [],
            "footer": {"copyright_notices": "<Copyright notices>", "notices": "<notices>"},
        }

        i = 0
        while i < len(lines) and not _is_major_separator(lines[i]):
            i += 1
        if i < len(lines):
            i += 1

        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines) and not _is_minor_separator(lines[i]):
            doc["header"]["package_name"] = lines[i].strip()
            i += 1

        while i < len(lines):
            if _is_footer_marker(lines[i]):
                doc["footer"], i = self._parse_footer(lines, i)
                break

            if not _is_major_separator(lines[i]):
                i += 1
                continue

            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                break

            section_name = lines[i].strip()
            i += 1
            while i < len(lines) and not _is_minor_separator(lines[i]):
                i += 1
            if i < len(lines):
                i += 1

            section: dict[str, Any] = {"name": section_name, "blocks": []}
            first_block = True
            while i < len(lines):
                if _is_footer_marker(lines[i]):
                    doc["footer"], i = self._parse_footer(lines, i)
                    if section["blocks"]:
                        doc["sections"].append(section)
                    return doc

                if _is_major_separator(lines[i]):
                    break

                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i >= len(lines) or _is_major_separator(lines[i]) or _is_footer_marker(lines[i]):
                    break

                if first_block:
                    first_block = False
                else:
                    if not _is_minor_separator(lines[i]):
                        i += 1
                        continue
                    i += 1
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                    if i >= len(lines) or _is_major_separator(lines[i]) or _is_footer_marker(lines[i]):
                        break

                block_name = lines[i].strip()
                i += 1
                text_lines: list[str] = []
                while i < len(lines):
                    if _is_minor_separator(lines[i]) or _is_major_separator(lines[i]):
                        break
                    if _is_footer_marker(lines[i]):
                        break
                    text_lines.append(lines[i])
                    i += 1
                section["blocks"].append({
                    "name": block_name,
                    "text": "\n".join(text_lines).strip(),
                })

            if section["blocks"] or section_name in _SECTION_NAMES:
                doc["sections"].append(section)

        return doc

    def entries(self, doc: dict[str, Any]) -> Iterable[Entry]:
        if self._primary_doc is None:
            self._primary_doc = copy.deepcopy(doc)

        for section in doc.get("sections", []):
            for block in section.get("blocks", []):
                data = copy.deepcopy(block)
                data["section"] = section.get("name", "")
                yield Entry(data=data, kind=EntryKind.LICENSE_TEXT, source_id="")

    def identity(self, entry: Entry) -> str:
        text = entry.data.get("text", "")
        return compute_text_identity(normalize_readmeoss_text(text))

    def local_refs(self, doc: dict[str, Any]) -> list[str]:
        return []

    def rewrite_refs(self, doc: dict[str, Any], remap: dict[str, str]) -> None:
        return

    def assemble(self, entries: list[Entry], metadata: dict[str, Any]) -> dict[str, Any]:
        section_order = self.mapping.raw.get(
            "section_order", list(_SECTION_NAMES)
        )
        sections_map: dict[str, list[dict[str, str]]] = {name: [] for name in section_order}

        for entry in entries:
            section_name = entry.data.get("section", "OTHER LICENSES")
            if section_name not in sections_map:
                sections_map[section_name] = []
            sections_map[section_name].append({
                "name": entry.data.get("name", ""),
                "text": entry.data.get("text", ""),
            })

        header = copy.deepcopy((self._primary_doc or {}).get("header", {}))
        footer = copy.deepcopy((self._primary_doc or {}).get("footer", {}))

        sections = []
        for name in section_order:
            blocks = sections_map.get(name, [])
            if blocks:
                sections.append({"name": name, "blocks": blocks})
        for name, blocks in sections_map.items():
            if name not in section_order and blocks:
                sections.append({"name": name, "blocks": blocks})

        return {"header": header, "sections": sections, "footer": footer}

    def render(self, doc: dict[str, Any]) -> bytes:
        lines: list[str] = []
        lines.append(_MAJOR_SEP)
        lines.append("")
        lines.append(doc.get("header", {}).get("package_name", ""))
        lines.append("")
        lines.append(_MINOR_SEP)
        lines.append("")

        for section in doc.get("sections", []):
            lines.append(_MAJOR_SEP)
            lines.append("")
            lines.append(f" {section.get('name', '')} ")
            lines.append("")
            lines.append(_MINOR_SEP)
            lines.append("")

            for block_idx, block in enumerate(section.get("blocks", [])):
                if block_idx > 0:
                    lines.append(_MINOR_SEP)
                    lines.append("")
                lines.append(block.get("name", ""))
                lines.append("")
                text = block.get("text", "")
                if text:
                    lines.extend(text.split("\n"))
                lines.append("")

        footer = doc.get("footer", {})
        lines.append(_MINOR_SEP)
        lines.append("")
        lines.append(footer.get("copyright_notices", "<Copyright notices>"))
        lines.append("")
        lines.append(footer.get("notices", "<notices>"))
        if not footer.get("notices"):
            lines.append("")

        return "\n".join(lines).encode("utf-8")
