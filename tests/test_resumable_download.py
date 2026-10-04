from __future__ import annotations

import io
from pathlib import Path

import pytest

from underpayment_checker.exceptions import DownloadError
from underpayment_checker.ingestion import resumable_download

PAYLOAD = b"0123456789" * 1000


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int, length: int | None = None) -> None:
        super().__init__(body)
        self.status = status
        self.headers = {"Content-Length": str(len(body) if length is None else length)}


def _opener(requests: list, *, honour_range: bool = True, truncate: int = 0):
    def open_(request):
        requests.append(request)
        range_header = request.get_header("Range")
        if range_header and honour_range:
            start = int(range_header.split("=")[1].rstrip("-"))
            return FakeResponse(PAYLOAD[start:], 206)
        body = PAYLOAD[: len(PAYLOAD) - truncate]
        return FakeResponse(body, 200, length=len(PAYLOAD))

    return open_


def test_fresh_download(tmp_path: Path) -> None:
    dest = tmp_path / "file.gz"
    requests: list = []
    resumable_download.download("https://x.test/f", dest, opener=_opener(requests))
    assert dest.read_bytes() == PAYLOAD
    assert requests[0].get_header("Range") is None


def test_resumes_partial_file(tmp_path: Path) -> None:
    dest = tmp_path / "file.gz"
    dest.write_bytes(PAYLOAD[:4000])
    requests: list = []
    resumable_download.download("https://x.test/f", dest, opener=_opener(requests))
    assert dest.read_bytes() == PAYLOAD
    assert requests[0].get_header("Range") == "bytes=4000-"


def test_restarts_when_server_ignores_range(tmp_path: Path) -> None:
    dest = tmp_path / "file.gz"
    dest.write_bytes(b"garbage")
    resumable_download.download("https://x.test/f", dest, opener=_opener([], honour_range=False))
    assert dest.read_bytes() == PAYLOAD


def test_truncated_download_raises(tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="expected"):
        resumable_download.download(
            "https://x.test/f", tmp_path / "file.gz", opener=_opener([], truncate=10)
        )
