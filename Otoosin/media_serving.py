"""Narrow fallback for serving uploaded media when no proxy serves it.

This is intentionally not a production-grade media architecture. WhiteNoise
only serves collected static files, so a deployment without an object store or
reverse-proxy media mapping needs an application route to verify that uploaded
files are present and reachable.
"""

from pathlib import Path

from django.conf import settings
from django.http import (
    FileResponse,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
)


def _not_found():
    return HttpResponseNotFound("Not Found", content_type="text/plain")


def serve_media(request, path):
    if request.method not in {"GET", "HEAD"}:
        return HttpResponseNotAllowed(["GET", "HEAD"])

    media_root = Path(settings.MEDIA_ROOT).resolve()
    try:
        candidate = (media_root / path).resolve()
        candidate.relative_to(media_root)
    except (OSError, ValueError):
        return _not_found()

    if not candidate.is_file():
        return _not_found()

    try:
        file_handle = candidate.open("rb")
    except OSError:
        return _not_found()

    return FileResponse(file_handle)
