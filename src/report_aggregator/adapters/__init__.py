"""Format adapters — one per FOSSology report format."""


def get_adapter_class(format_name: str):
    """Get adapter class for a format name."""
    if format_name == "cyclonedx":
        from .cyclonedx import CycloneDXAdapter
        return CycloneDXAdapter
    elif format_name == "spdx2tv":
        from .spdx2tv import SPDX2TVAdapter
        return SPDX2TVAdapter
    elif format_name == "dep5":
        from .dep5 import DEP5Adapter
        return DEP5Adapter
    elif format_name == "readmeoss":
        from .readmeoss import ReadMeOSSAdapter
        return ReadMeOSSAdapter
    elif format_name == "spdx3json":
        from .spdx3json import SPDX3JSONAdapter
        return SPDX3JSONAdapter
    else:
        raise ValueError(f"Unknown format: {format_name}")

