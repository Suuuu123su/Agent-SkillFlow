"""Read sealed relative paths without changing their strings or digest."""
from pathlib import Path, PureWindowsPath


def confined(root, relative):
    if not isinstance(relative, str) or not relative or '\x00' in relative:
        raise ValueError('Invalid relative path')
    windows = PureWindowsPath(relative)
    normalized = relative.replace('\\', '/')
    parts = normalized.split('/')
    if windows.drive or windows.root or normalized.startswith('/'):
        raise ValueError('Absolute paths and drive paths are forbidden')
    if any(p in ('', '.', '..') or ':' in p for p in parts):
        raise ValueError('Noncanonical relative path')
    root = Path(root).resolve()
    path = root.joinpath(*parts).resolve()
    if root not in path.parents:
        raise ValueError('Resolved path escapes root')
    return path
