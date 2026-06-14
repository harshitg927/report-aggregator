"""Adapter base — Protocol definition for format adapters.

Every format adapter implements this interface. The merge engine calls these
methods without knowing anything about the underlying format.

Architecture reference: §3.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Protocol


class EntryKind(Enum):
    """Discriminator for the type of mergeable entry."""

    PACKAGE = "package"
    FILE = "file"
    LICENSE_TEXT = "license_text"
    STANZA = "stanza"


@dataclass
class Entry:
    """A single mergeable entry extracted from a report.

    Attributes:
        data: The native format structure for this entry (dict, XML element, etc.).
        kind: Whether this is a package, file, or license text block.
        source_id: Identifier of the input report this entry came from.
        identity_key: Computed identity for grouping (SHA1 hash, md5(text), etc.).
    """

    data: Any
    kind: EntryKind
    source_id: str
    identity_key: str = ""


class FormatAdapter(Protocol):
    """Protocol that every format adapter must implement.

    Adapters know only their own format. All reusable merge logic lives
    in the engine.
    """

    def load(self, raw: bytes) -> Any:
        """Parse a FOSSology report file into its native structure.

        Args:
            raw: Raw bytes of the report file.

        Returns:
            Native structure (dict for JSON, parsed tree for XML, etc.).
        """
        ...

    def entries(self, doc: Any) -> Iterable[Entry]:
        """Extract normalized mergeable entries from a loaded document.

        Must handle multi-package/multi-root inputs by expanding them
        (architecture §2.3).

        Args:
            doc: The native structure returned by load().

        Yields:
            Entry objects with kind and data populated (identity_key filled by engine).
        """
        ...

    def identity(self, entry: Entry) -> str:
        """Compute the merge identity key for an entry.

        Uses the rules from the mapping file and §4.1:
        - Packages/files: SHA1 (lowercased hex)
        - License text: md5(normalized_text)

        Args:
            entry: An entry extracted by entries().

        Returns:
            Identity string for grouping.
        """
        ...

    def local_refs(self, doc: Any) -> list[str]:
        """Collect all document-local IDs that need re-namespacing.

        For graph formats: SPDXRef-*, bom-ref values.
        For stanza formats: return empty list (no ref graph).

        Args:
            doc: The native structure.

        Returns:
            List of local reference strings.
        """
        ...

    def rewrite_refs(self, doc: Any, remap: dict[str, str]) -> None:
        """Apply a ref remapping table to the document.

        For graph formats: update SPDXRef-* / bom-ref values and any
        cross-references (relationships, license links, etc.).
        For stanza formats: no-op.

        Args:
            doc: The native structure (modified in-place).
            remap: Mapping of old_ref → new_ref.
        """
        ...

    def assemble(
        self,
        entries: list[Entry],
        metadata: dict[str, Any],
    ) -> Any:
        """Build a single output document from merged entries.

        Constructs the document wrapper (metadata, header, etc.) and
        places the merged entries into the correct locations.

        Args:
            entries: Merged entries to include in the output.
            metadata: Merge metadata (input info, tools, timestamps, etc.).

        Returns:
            The assembled native structure, ready for render().
        """
        ...

    def render(self, doc: Any) -> bytes:
        """Serialize the native structure back to the report format.

        Args:
            doc: The assembled native structure.

        Returns:
            Raw bytes of the rendered report file.
        """
        ...
