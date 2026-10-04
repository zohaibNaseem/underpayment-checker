"""Download multi-gigabyte rate files over HTTP. Continue a download that stopped."""

from __future__ import annotations

import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from underpayment_checker.exceptions import DownloadError

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (underpayment-checker)"
CHUNK_SIZE = 1 << 20  # 1 MiB

Opener = Callable[[urllib.request.Request], BinaryIO]


def _default_opener(request: urllib.request.Request) -> BinaryIO:
    return urllib.request.urlopen(request, timeout=120)


def download(url: str, dest: Path, *, opener: Opener = _default_opener) -> Path:
    """Download ``url`` to ``dest``. If a partial file exists, continue from its end.

    Raises:
        DownloadError: if the file size on disk is not the size that the server gave.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    start = dest.stat().st_size if dest.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if start:
        headers["Range"] = f"bytes={start}-"
        logger.info("Resuming %s at byte %d", dest.name, start)

    with opener(urllib.request.Request(url, headers=headers)) as response:
        if start and getattr(response, "status", 200) != 206:
            logger.warning("Server ignored the range request; restarting the download")
            start = 0
        remaining = int(response.headers.get("Content-Length") or 0)
        expected = start + remaining if remaining else None
        with dest.open("ab" if start else "wb") as handle:
            while chunk := response.read(CHUNK_SIZE):
                handle.write(chunk)

    actual = dest.stat().st_size
    if expected is not None and actual != expected:
        raise DownloadError(f"{dest.name}: expected {expected} bytes, got {actual}")
    logger.info("Downloaded %s (%d bytes)", dest.name, actual)
    return dest
