#!/usr/bin/env python3
"""Legacy HTTP API entry point — DEPRECATED since v3.

This module previously ran a stdlib ``http.server`` implementation. It now
delegates to the v3 FastAPI app. Prefer the supported entry point::

    silhouette serve

Or::

    python -m silhouette.cli serve
"""

from __future__ import annotations

import warnings


def main() -> None:
    warnings.warn(
        "src/api/enhanced_memory_api.py is deprecated since v3. "
        "Use `silhouette serve` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    import uvicorn

    from silhouette.api import create_app
    from silhouette.config import get_settings

    settings = get_settings()
    uvicorn.run(create_app(), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
