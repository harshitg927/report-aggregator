# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""RFC-6902 JSON Patch implementation for edit layer."""

from dataclasses import dataclass
from typing import Any


class PatchError(Exception):
    """Base exception for patch operations."""


class PatchPathError(PatchError):
    """Path doesn't exist or is invalid."""


class PatchTestFailed(PatchError):
    """Test operation failed (value mismatch)."""


class PatchValidationError(PatchError):
    """Patch failed validation."""


@dataclass
class Patch:
    """RFC-6902 JSON Patch operation."""
    op: str  # "add" | "remove" | "replace" | "move" | "copy" | "test"
    path: str  # JSON Pointer: "/packages/0/copyrightText"
    value: Any = None  # For add/replace/test
    from_: str = ""  # For move/copy (JSON Pointer)


def parse_json_pointer(path: str) -> list[str | int]:
    """Parse JSON Pointer path into tokens.
    
    Args:
        path: JSON Pointer string starting with '/'
        
    Returns:
        List of path tokens (strings or integers for array indices)
        
    Raises:
        PatchValidationError: If path is invalid
    """
    if not path:
        return []
    
    if not path.startswith('/'):
        raise PatchValidationError(f"Invalid JSON Pointer (must start with '/'): {path}")
    
    if path == '/':
        return []
    
    tokens = []
    for part in path[1:].split('/'):
        # Unescape ~1 to / and ~0 to ~
        part = part.replace('~1', '/').replace('~0', '~')
        
        # Try to parse as array index
        try:
            tokens.append(int(part))
        except ValueError:
            tokens.append(part)
    
    return tokens


def navigate_to(doc: Any, tokens: list[str | int], create_parents: bool = False) -> tuple[Any, Any, str | int]:
    """Navigate to a path in document, returning (parent, container, key).
    
    Args:
        doc: Document to navigate
        tokens: Parsed JSON Pointer tokens
        create_parents: If True, create missing parent objects/arrays
        
    Returns:
        Tuple of (parent container, immediate container, final key)
        
    Raises:
        PatchPathError: If path doesn't exist or type mismatch
    """
    if not tokens:
        return None, None, None
    
    current = doc
    
    for i, token in enumerate(tokens[:-1]):
        if isinstance(current, dict):
            if token not in current:
                if create_parents:
                    # Create parent - guess list if next token is int, else dict
                    next_token = tokens[i + 1]
                    current[token] = [] if isinstance(next_token, int) else {}
                else:
                    raise PatchPathError(f"Path not found: missing key '{token}'")
            current = current[token]
        elif isinstance(current, list):
            if not isinstance(token, int):
                raise PatchPathError(f"Cannot index list with non-integer: {token}")
            if token < 0 or token >= len(current):
                raise PatchPathError(f"Array index out of bounds: {token}")
            current = current[token]
        else:
            raise PatchPathError(f"Cannot navigate into non-container type at '{token}'")
    
    final_key = tokens[-1]
    parent = current
    
    return doc, parent, final_key


def path_exists(doc: Any, path: str) -> bool:
    """Check if a path exists in the document."""
    try:
        tokens = parse_json_pointer(path)
        if not tokens:
            return True
        _, parent, key = navigate_to(doc, tokens)
        if isinstance(parent, dict):
            return key in parent
        elif isinstance(parent, list):
            return isinstance(key, int) and 0 <= key < len(parent)
        return False
    except (PatchPathError, PatchValidationError):
        return False


def validate_patch(patch: Patch, doc: Any = None) -> None:
    """Validate patch structure and operation.
    
    Args:
        patch: Patch to validate
        doc: Optional document for path existence checks
        
    Raises:
        PatchValidationError: If patch is invalid
    """
    valid_ops = {"add", "remove", "replace", "move", "copy", "test"}
    if patch.op not in valid_ops:
        raise PatchValidationError(f"Invalid operation: {patch.op}")
    
    # Validate path syntax
    try:
        parse_json_pointer(patch.path)
    except Exception as e:
        raise PatchValidationError(f"Invalid path: {e}")
    
    # Validate operation-specific requirements
    if patch.op in {"add", "replace", "test"}:
        if patch.value is None:
            raise PatchValidationError(f"{patch.op} requires 'value'")
    
    if patch.op in {"move", "copy"}:
        if not patch.from_:
            raise PatchValidationError(f"{patch.op} requires 'from' path")
        try:
            parse_json_pointer(patch.from_)
        except Exception as e:
            raise PatchValidationError(f"Invalid 'from' path: {e}")
    
    # Check path existence for operations that require it
    if doc is not None and patch.op in {"remove", "replace", "test"}:
        if not path_exists(doc, patch.path):
            raise PatchPathError(f"Path does not exist: {patch.path}")


def apply_add(doc: Any, tokens: list[str | int], value: Any) -> Any:
    """Apply 'add' operation."""
    if not tokens:
        return value
    
    _, parent, key = navigate_to(doc, tokens, create_parents=True)
    
    if isinstance(parent, dict):
        parent[key] = value
    elif isinstance(parent, list):
        if not isinstance(key, int):
            raise PatchPathError(f"Cannot index list with non-integer: {key}")
        if key == len(parent):
            parent.append(value)
        elif 0 <= key < len(parent):
            parent.insert(key, value)
        else:
            raise PatchPathError(f"Array index out of bounds: {key}")
    else:
        raise PatchPathError(f"Cannot add to non-container type")
    
    return doc


def apply_remove(doc: Any, tokens: list[str | int]) -> Any:
    """Apply 'remove' operation."""
    if not tokens:
        raise PatchPathError("Cannot remove root document")
    
    _, parent, key = navigate_to(doc, tokens)
    
    if isinstance(parent, dict):
        if key not in parent:
            raise PatchPathError(f"Key not found: {key}")
        del parent[key]
    elif isinstance(parent, list):
        if not isinstance(key, int):
            raise PatchPathError(f"Cannot index list with non-integer: {key}")
        if key < 0 or key >= len(parent):
            raise PatchPathError(f"Array index out of bounds: {key}")
        parent.pop(key)
    else:
        raise PatchPathError("Cannot remove from non-container type")
    
    return doc


def apply_replace(doc: Any, tokens: list[str | int], value: Any) -> Any:
    """Apply 'replace' operation."""
    if not tokens:
        return value
    
    _, parent, key = navigate_to(doc, tokens)
    
    if isinstance(parent, dict):
        if key not in parent:
            raise PatchPathError(f"Key not found: {key}")
        parent[key] = value
    elif isinstance(parent, list):
        if not isinstance(key, int):
            raise PatchPathError(f"Cannot index list with non-integer: {key}")
        if key < 0 or key >= len(parent):
            raise PatchPathError(f"Array index out of bounds: {key}")
        parent[key] = value
    else:
        raise PatchPathError("Cannot replace in non-container type")
    
    return doc


def get_value_at_path(doc: Any, tokens: list[str | int]) -> Any:
    """Get value at a path in the document."""
    if not tokens:
        return doc
    
    _, parent, key = navigate_to(doc, tokens)
    
    if isinstance(parent, dict):
        if key not in parent:
            raise PatchPathError(f"Key not found: {key}")
        return parent[key]
    elif isinstance(parent, list):
        if not isinstance(key, int):
            raise PatchPathError(f"Cannot index list with non-integer: {key}")
        if key < 0 or key >= len(parent):
            raise PatchPathError(f"Array index out of bounds: {key}")
        return parent[key]
    else:
        raise PatchPathError("Cannot get value from non-container type")


def apply_move(doc: Any, from_tokens: list[str | int], to_tokens: list[str | int]) -> Any:
    """Apply 'move' operation."""
    # Get value from source
    value = get_value_at_path(doc, from_tokens)
    
    # Remove from source
    doc = apply_remove(doc, from_tokens)
    
    # Add to destination
    doc = apply_add(doc, to_tokens, value)
    
    return doc


def apply_copy(doc: Any, from_tokens: list[str | int], to_tokens: list[str | int]) -> Any:
    """Apply 'copy' operation."""
    # Get value from source (don't remove)
    value = get_value_at_path(doc, from_tokens)
    
    # Add to destination
    doc = apply_add(doc, to_tokens, value)
    
    return doc


def apply_test(doc: Any, tokens: list[str | int], expected: Any) -> None:
    """Apply 'test' operation.
    
    Raises:
        PatchTestFailed: If value doesn't match expected
    """
    actual = get_value_at_path(doc, tokens)
    
    if actual != expected:
        raise PatchTestFailed(f"Test failed: expected {expected}, got {actual}")


def apply_patch(doc: Any, patch: Patch) -> Any:
    """Apply a single patch operation to a document.
    
    Args:
        doc: Document to patch (will be modified in place)
        patch: Patch operation to apply
        
    Returns:
        Modified document
        
    Raises:
        PatchError: If patch application fails
    """
    validate_patch(patch, doc)
    tokens = parse_json_pointer(patch.path)
    
    if patch.op == "add":
        return apply_add(doc, tokens, patch.value)
    elif patch.op == "remove":
        return apply_remove(doc, tokens)
    elif patch.op == "replace":
        return apply_replace(doc, tokens, patch.value)
    elif patch.op == "move":
        from_tokens = parse_json_pointer(patch.from_)
        return apply_move(doc, from_tokens, tokens)
    elif patch.op == "copy":
        from_tokens = parse_json_pointer(patch.from_)
        return apply_copy(doc, from_tokens, tokens)
    elif patch.op == "test":
        apply_test(doc, tokens, patch.value)
        return doc
    
    raise PatchValidationError(f"Unknown operation: {patch.op}")


def apply_patches(doc: Any, patches: list[Patch]) -> Any:
    """Apply a list of patches sequentially.
    
    Args:
        doc: Document to patch
        patches: List of patches to apply in order
        
    Returns:
        Modified document
        
    Raises:
        PatchError: If any patch fails
    """
    for patch in patches:
        doc = apply_patch(doc, patch)
    return doc


def apply_document_patch(
    doc: Any,
    patch: Patch,
    load_from_bytes: Any | None = None,
) -> Any:
    """Apply a provenance edit patch, including full-document text replacements.

    Document-editor saves for formats with non-JSON-native structures (CLIXML)
    record ``replace`` at ``/`` with the raw edited file text. When
    ``load_from_bytes`` is provided (typically ``adapter.load``), that path
    re-parses the text instead of assigning a string to the native document.
    """
    if (
        load_from_bytes is not None
        and patch.op == "replace"
        and patch.path == "/"
        and isinstance(patch.value, str)
    ):
        return load_from_bytes(patch.value.encode("utf-8"))
    return apply_patch(doc, patch)


def apply_document_patches(
    doc: Any,
    patches: list[Patch],
    load_from_bytes: Any | None = None,
) -> Any:
    """Apply provenance edits sequentially, with document-text replacement support."""
    for patch in patches:
        doc = apply_document_patch(doc, patch, load_from_bytes)
    return doc
