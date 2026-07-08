"""Dataset acquisition — download a benchmark file from a URL into RAW_DIR.

Accepts direct .json / .jsonl links and .tgz archives (QASPER's release format —
contained .json/.jsonl members are extracted flat, nothing else). Hugging Face
`/blob/` page URLs are rewritten to `/resolve/` raw URLs so pasting the browser
address bar just works. Progress streams as events for the page.
"""

from __future__ import annotations

import re
import tarfile
import urllib.request
from typing import Iterator
from urllib.parse import urlparse

from app.bench.store import RAW_DIR

_CHUNK = 1 << 20  # 1 MB
_OK_SUFFIXES = (".json", ".jsonl", ".tgz", ".tar.gz")


def _normalize(url: str) -> str:
    if "huggingface.co" in url and "/blob/" in url:
        url = url.replace("/blob/", "/resolve/")
    return url


_HF_REPO = re.compile(r"^https?://huggingface\.co/datasets/([^/]+)/([^/?#]+)/?$")


def _resolve_repo(url: str) -> list[dict] | None:
    """A bare HF dataset-page URL -> the repo's downloadable data files (or None if
    the URL isn't a repo page). Filters to formats the bench can ingest."""
    m = _HF_REPO.match(url.strip())
    if not m:
        return None
    org, name = m.groups()
    api = f"https://huggingface.co/api/datasets/{org}/{name}/tree/main?recursive=true"
    req = urllib.request.Request(api, headers={"User-Agent": "noema-bench/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        import json
        tree = json.loads(resp.read())
    out = []
    for f in tree:
        path = f.get("path", "")
        base = path.rsplit("/", 1)[-1]
        if base in ("dataset_infos.json", "config.json"):  # HF plumbing, not data
            continue
        if f.get("type") == "file" and path.endswith(_OK_SUFFIXES):
            out.append({
                "name": path,
                "mb": round((f.get("size") or 0) / 1e6, 1),
                "url": f"https://huggingface.co/datasets/{org}/{name}/resolve/main/{path}",
            })
    return out


def _filename(url: str) -> str:
    name = urlparse(url).path.rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if not name or not name.endswith(_OK_SUFFIXES):
        raise ValueError("URL must point to a .json, .jsonl or .tgz file.")
    return name


def _extract_archive(archive_path) -> list[str]:
    """Pull .json/.jsonl members out of a tgz, flat into RAW_DIR (no paths kept)."""
    extracted = []
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            base = member.name.rsplit("/", 1)[-1]
            if not (member.isfile() and base.endswith((".json", ".jsonl"))):
                continue
            src = tar.extractfile(member)
            if src is None:
                continue
            dest = RAW_DIR / base
            with open(dest, "wb") as out:
                while chunk := src.read(_CHUNK):
                    out.write(chunk)
            extracted.append(base)
    archive_path.unlink()
    return extracted


def download(url: str) -> Iterator[dict]:
    """Yield progress events while fetching `url` into RAW_DIR."""
    url = _normalize(url.strip())
    if urlparse(url).scheme not in ("http", "https"):
        yield {"phase": "error", "detail": "Only http(s) URLs are supported."}
        return

    try:
        candidates = _resolve_repo(url)
    except Exception as exc:  # noqa: BLE001
        yield {"phase": "error", "detail": f"Could not list the repository: {exc}"}
        return
    if candidates is not None:
        if not candidates:
            yield {"phase": "error", "detail": (
                "This repository hosts no downloadable data files (some datasets only "
                "carry a loader script) — paste the direct file link instead.")}
            return
        if len(candidates) > 1:
            yield {"phase": "choices", "files": candidates}
            return
        url = candidates[0]["url"]  # exactly one usable file: just take it

    try:
        name = _filename(url)
    except ValueError as exc:
        yield {"phase": "error", "detail": str(exc)}
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    part = RAW_DIR / (name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "noema-bench/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            yield {"phase": "download_start", "file": name,
                   "total_mb": round(total / 1e6, 1) if total else None}
            done = 0
            while chunk := resp.read(_CHUNK):
                out.write(chunk)
                done += len(chunk)
                yield {"phase": "progress", "mb": round(done / 1e6, 1),
                       "total_mb": round(total / 1e6, 1) if total else None}
    except Exception as exc:  # noqa: BLE001 — network errors become one clean event
        part.unlink(missing_ok=True)
        yield {"phase": "error", "detail": f"Download failed: {exc}"}
        return

    final = RAW_DIR / name
    part.replace(final)
    if name.endswith((".tgz", ".tar.gz")):
        try:
            files = _extract_archive(final)
        except Exception as exc:  # noqa: BLE001
            yield {"phase": "error", "detail": f"Archive extraction failed: {exc}"}
            return
        yield {"phase": "done", "files": files, "extracted": True}
    else:
        yield {"phase": "done", "files": [name], "extracted": False}
