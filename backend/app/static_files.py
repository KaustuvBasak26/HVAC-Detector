from __future__ import annotations

from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles


class SecureStaticFiles(StaticFiles):
    """Serve the SPA build while blocking source maps and other sensitive artifacts."""

    _blocked_suffixes = {".map", ".ts", ".tsx", ".jsx", ".env", ".git", ".md"}

    async def get_response(self, path: str, scope):
        normalized = Path(path)
        suffix = normalized.suffix.lower()
        if suffix in self._blocked_suffixes:
            return Response(status_code=404)
        if normalized.name.startswith("."):
            return Response(status_code=404)
        return await super().get_response(path, scope)
