"""Shared location resolver for the XBRL research caches."""

import os
from pathlib import Path


def xbrl_cache_root(local_default: Path) -> Path:
    """Return the configured XBRL cache root, or the original local path."""
    configured = os.environ.get("NORTHSTAR_XBRL_CACHE_ROOT")

    if not configured:
        return local_default

    root = Path(configured).expanduser()

    if not root.is_dir() or not root.is_mount():
        raise RuntimeError(
            "NORTHSTAR_XBRL_CACHE_ROOT is configured, but the cache "
            f"mount is unavailable: {root}"
        )

    return root
