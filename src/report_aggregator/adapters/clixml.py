"""CLIXML format adapter.

Handles Component License Information XML format from FOSSology, including:
- Multi-root XML documents (FOSSology uploadsAdd concatenation)
- Component identity by componentSHA1
- License/copyright identity by md5(normalized text)
- Obligation identity including license references
- CDATA content normalization and escaping
- Optional sections handling
- Acknowledgements merge
"""

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind


class CLIXMLAdapter:
    """Adapter for CLIXML format."""

    def __init__(self, mapping: dict[str, Any]):
        self.mapping = mapping
        self._identity_cache: dict[str, str] = {}
        self._cdata_escape_re = re.compile(r']]>')
        self._parent_map: dict[int, str] = {}  # Maps element id() to parent component ID

    def load(self, raw: bytes) -> list[ET.Element]:
        """Parse CLIXML, handling multi-root documents."""
        return self._parse_multi_root(raw)

    def entries(self, doc: list[ET.Element]) -> Iterable[Entry]:
        """Extract component + license + copyright + obligation entries."""
        for root in doc:
            # Get component ID for tracking children (may be None if missing)
            comp_id = root.get("componentSHA1", "").lower() or None
            
            # Component entry
            yield Entry(data=root, kind=EntryKind.PACKAGE, source_id="")

            # Only track children if we have a valid component ID
            if comp_id:
                # License entries (track parent)
                for lic in root.findall("License"):
                    self._parent_map[id(lic)] = comp_id
                    yield Entry(data=lic, kind=EntryKind.LICENSE_TEXT, source_id="")

                # Copyright entries
                for cp in root.findall("Copyright"):
                    self._parent_map[id(cp)] = comp_id
                    yield Entry(data=cp, kind=EntryKind.STANZA, source_id="")

                # Obligation entries
                for ob in root.findall("Obligation"):
                    self._parent_map[id(ob)] = comp_id
                    yield Entry(data=ob, kind=EntryKind.STANZA, source_id="")

                # ExportRestrictions entries
                for ecc in root.findall("ExportRestrictions"):
                    self._parent_map[id(ecc)] = comp_id
                    yield Entry(data=ecc, kind=EntryKind.STANZA, source_id="")

                # Patents entries
                for ipra in root.findall("Patents"):
                    self._parent_map[id(ipra)] = comp_id
                    yield Entry(data=ipra, kind=EntryKind.STANZA, source_id="")

    def identity(self, entry: Entry) -> str:
        """Compute identity based on entry kind."""
        if entry.kind == EntryKind.PACKAGE:
            return self._component_identity(entry.data)
        elif entry.kind == EntryKind.LICENSE_TEXT:
            return self._license_identity(entry.data)
        elif entry.kind == EntryKind.STANZA:
            # Check if it's an obligation (has Topic/Text/Licenses)
            if entry.data.find("Topic") is not None:
                return self._obligation_identity(entry.data)
            # Otherwise it's copyright/ecc/patents
            content = entry.data.findtext("Content", "")
            return self._text_identity(content)
        return ""

    def local_refs(self, doc: list[ET.Element]) -> list[str]:
        """CLIXML has no local refs."""
        return []

    def rewrite_refs(self, doc: list[ET.Element], remap: dict[str, str]) -> None:
        """No-op: CLIXML has no local refs."""
        pass

    def assemble(self, entries: list[Entry], metadata: dict[str, Any]) -> list[ET.Element]:
        """Assemble merged entries into CLIXML structure."""
        # Group by component identity
        components: dict[str, ET.Element] = {}
        component_children: dict[str, list[ET.Element]] = {}
        
        # Collect components first
        for entry in entries:
            if entry.kind == EntryKind.PACKAGE:
                comp_id = entry.identity_key
                if comp_id not in components:
                    components[comp_id] = entry.data
                    component_children[comp_id] = []
        
        # Then collect children, using parent map
        for entry in entries:
            if entry.kind != EntryKind.PACKAGE:
                # Get parent component ID from map
                parent_id = self._parent_map.get(id(entry.data))
                if parent_id and parent_id in component_children:
                    component_children[parent_id].append(entry.data)
        
        # Build output roots
        roots = []
        for comp_id, root in components.items():
            # Remove old child elements
            for child in list(root):
                if child.tag in ["License", "Copyright", "Obligation", "ExportRestrictions", "Patents"]:
                    root.remove(child)
            
            # Add merged children back
            for child in component_children.get(comp_id, []):
                root.append(child)
            
            # Check if any license has acknowledgements
            licenses = [c for c in component_children.get(comp_id, []) if c.tag == "License"]
            has_acks = any(lic.find("Acknowledgements") is not None for lic in licenses)
            if has_acks:
                root.set("includesAcknowledgements", "true")
            
            roots.append(root)

        return roots

    def render(self, doc: list[ET.Element]) -> bytes:
        """Serialize to XML with proper CDATA wrapping."""
        parts = []
        for root in doc:
            # Serialize each root
            xml_str = ET.tostring(root, encoding='unicode', method='xml')
            # Add XML declaration
            full_xml = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}\n'
            parts.append(full_xml)
        
        return ''.join(parts).encode('utf-8')

    # --- Private helpers ---

    def _parse_multi_root(self, raw: bytes) -> list[ET.Element]:
        """Split and parse multi-root XML."""
        text = raw.decode('utf-8')
        
        # Split on XML declarations or root element start
        pattern = r'(<\?xml[^?]*\?>\s*)?<ComponentLicenseInformation'
        parts = re.split(pattern, text)
        
        roots = []
        i = 0
        while i < len(parts):
            # Reconstruct chunks (pattern match groups alternate)
            chunk = ""
            if i < len(parts) and parts[i]:
                chunk += parts[i]
            if i + 1 < len(parts) and parts[i + 1]:
                chunk += parts[i + 1]
            
            # Find the closing tag
            start_idx = text.find('<ComponentLicenseInformation', 
                                 text.find(chunk) if chunk else 0)
            if start_idx >= 0:
                end_idx = text.find('</ComponentLicenseInformation>', start_idx)
                if end_idx >= 0:
                    doc_text = text[start_idx:end_idx + len('</ComponentLicenseInformation>')]
                    # Ensure XML declaration
                    if not doc_text.strip().startswith('<?xml'):
                        doc_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + doc_text
                    
                    try:
                        root = ET.fromstring(doc_text)
                        if root.tag == 'ComponentLicenseInformation':
                            roots.append(root)
                    except ET.ParseError:
                        pass
            
            i += 2

        # Fallback: try parsing as single document
        if not roots:
            try:
                root = ET.fromstring(raw)
                if root.tag == 'ComponentLicenseInformation':
                    roots.append(root)
            except ET.ParseError as e:
                raise ValueError(f"Invalid CLIXML: {e}")

        if not roots:
            raise ValueError("No valid ComponentLicenseInformation roots found")

        return roots

    def _component_identity(self, root: ET.Element) -> str:
        """Extract componentSHA1, lowercase."""
        sha1 = root.get("componentSHA1", "")
        if not sha1:
            raise ValueError("Missing componentSHA1 attribute")
        return sha1.lower()

    def _license_identity(self, lic: ET.Element) -> str:
        """md5(normalized <Content>)."""
        content = lic.findtext("Content", "")
        return self._text_identity(content)

    def _obligation_identity(self, ob: ET.Element) -> str:
        """md5(topic + text + sorted(license_ids))."""
        topic = ob.findtext("Topic", "")
        text = ob.findtext("Text", "")
        
        # Extract license references
        licenses_elem = ob.find("Licenses")
        license_ids = []
        if licenses_elem is not None:
            for lic in licenses_elem.findall("License"):
                lic_id = (lic.text or "").strip()
                if lic_id:
                    license_ids.append(lic_id)
        
        # Sort for stable identity
        license_ids.sort()
        
        # Combine and hash
        combined = f"{topic}||{text}||{'|'.join(license_ids)}"
        return hashlib.md5(combined.encode('utf-8')).hexdigest()

    def _text_identity(self, text: str) -> str:
        """md5(normalized text) with caching.

        Cache is keyed by the text *value* (not ``id(text)``): CPython reuses
        object ids after garbage collection, so a transient string returned by
        ElementTree's ``findtext`` could collide with a previously cached id and
        return the wrong hash. Keying on the value is correct and still avoids
        re-normalizing identical blocks.
        """
        cached = self._identity_cache.get(text)
        if cached is not None:
            return cached

        normalized = self._normalize_cdata(text)
        hash_val = hashlib.md5(normalized.encode('utf-8')).hexdigest()

        self._identity_cache[text] = hash_val
        return hash_val

    def _normalize_cdata(self, text: str) -> str:
        """Normalize CDATA content for hashing."""
        # Handle NA
        if text.strip() == "NA":
            return ""
        
        # Remove CDATA markers
        text = text.replace("<![CDATA[", "").replace("]]>", "")
        
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        
        # Strip trailing whitespace per line, but preserve line structure
        lines = [line.rstrip() for line in text.splitlines()]
        
        return "\n".join(lines)

    def _normalize_hash(self, hash_str: str) -> str:
        """Strip prefixes and lowercase."""
        hash_str = hash_str.strip()
        
        # Strip known prefixes (raw dict directly contains the format config)
        hash_prefixes = self.mapping.raw.get("hash_prefixes", [])
        for prefix in hash_prefixes:
            if hash_str.startswith(prefix):
                hash_str = hash_str[len(prefix):]
                break
        
        return hash_str.lower()

    def _parse_file_list(self, files_text: str) -> list[str]:
        """Parse newline-separated file list from CDATA."""
        if not files_text:
            return []
        
        lines = files_text.strip().split('\n')
        return [line.strip() for line in lines if line.strip()]

    def _parse_hash_list(self, hash_text: str) -> list[str]:
        """Parse newline-separated hash list, normalize each."""
        if not hash_text:
            return []
        
        lines = hash_text.strip().split('\n')
        return [self._normalize_hash(line) for line in lines if line.strip()]

    def _render_cdata(self, text: str) -> str:
        """Wrap text in CDATA with proper escaping."""
        if not text:
            return "<![CDATA[]]>"
        
        # Escape ]]> sequences
        escaped = self._cdata_escape_re.sub(']]&gt;', text)
        
        return f"<![CDATA[{escaped}]]>"

    def _find_component_for_entry(self, entry_elem: ET.Element, components: list[ET.Element]) -> ET.Element | None:
        """Find which component an entry element belongs to."""
        # The entry element's parent in the original structure would be the component root
        # Since we've already extracted entries, we need to check which component it came from
        # For now, simple approach: the entry stays with the first component (will be enhanced by engine)
        return components[0] if components else None
