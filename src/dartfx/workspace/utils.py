"""
General utilities for dartfx-workspace.
"""


def format_size(size_bytes: int) -> str:
    """Formats bytes into human-friendly units (1.2MB, 4.5KB, etc.)."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    size: float = float(size_bytes)
    for unit in ["K", "M", "G", "T", "P"]:
        size /= 1024
        if size < 1024:
            return f"{size:.1f}{unit}"
    return f"{size:.1f}E"
