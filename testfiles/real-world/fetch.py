#!/usr/bin/env python3
"""
fetch.py - arxiv corpus fetcher for codependent.sty real-world integration tests.

Downloads a fixed set of arxiv paper source tarballs as declared in
corpus.lock. Verifies sha256, extracts into papers/<id>/, writes a
.fetched sentinel.

Usage:
  python fetch.py                       # fetch all papers per manifest
  python fetch.py <id> [<id> ...]       # fetch specific papers
  python fetch.py --list                # print manifest, no download
  python fetch.py --clean               # remove papers/ (prompts)
  python fetch.py --accept-pending <id> # download even if sha is PENDING_FETCH
                                        # (prints observed sha to stderr)

Design notes:
  - Python standard library only. No requests, no arxiv package.
  - Uses https://export.arxiv.org/e-print/<id>v<ver> which returns a
    tar.gz source tarball. Rate-limit policy: arxiv's "be nice" rule
    asks for AT MOST 4 requests per second. We use a hard 300 ms sleep
    between requests (~3.3 req/s, conservative).
  - User-Agent identifies the project per arxiv's request.
  - Idempotent: already-fetched papers (matching sha) are skipped.
  - Exits non-zero on any download or verification failure.

This script is self-contained and can be run from anywhere under
testfiles/real-world/. All paths are resolved relative to THIS
script's directory, not the CWD.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration -----------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
CORPUS_LOCK = SCRIPT_DIR / "corpus.lock"
PAPERS_DIR = SCRIPT_DIR / "papers"

ARXIV_EPRINT_BASE = "https://export.arxiv.org/e-print"
USER_AGENT = "codependent test corpus / codependent-arxiv-corpus 0.1"

# arxiv "be nice" policy: max 4 req/s. We use ~3.3 req/s (300 ms gap).
REQUEST_GAP_SECONDS = 0.3

# Max download size (sanity check, 128 MiB).
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024


# --- Helpers -----------------------------------------------------------


def log(msg: str) -> None:
    """Log to stderr (stdout is reserved for --list output)."""
    print(msg, file=sys.stderr, flush=True)


def load_manifest() -> dict:
    if not CORPUS_LOCK.exists():
        log(f"ERROR: corpus.lock not found at {CORPUS_LOCK}")
        sys.exit(2)
    try:
        with CORPUS_LOCK.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log(f"ERROR: corpus.lock is not valid JSON: {e}")
        sys.exit(2)


def arxiv_url(paper_id: str, version: str) -> str:
    # /e-print/<id>v<ver> returns the source tarball.
    # The `v` prefix is NOT repeated — version is like "v2", so we
    # strip the leading `v` and re-append to make /e-print/<id>v<n>.
    ver_num = version.lstrip("v")
    return f"{ARXIV_EPRINT_BASE}/{paper_id}v{ver_num}"


def download(url: str, dest: Path) -> None:
    """Download `url` to `dest`, enforcing MAX_DOWNLOAD_BYTES."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            size = 0
            with dest.open("wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(
                            f"download exceeded MAX_DOWNLOAD_BYTES "
                            f"({MAX_DOWNLOAD_BYTES}) at {size} bytes"
                        )
                    out.write(chunk)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error fetching {url}: {e.reason}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract(tar_path: Path, dest_dir: Path) -> None:
    """Extract a tarball safely, refusing path traversal."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    # arxiv source "tarballs" are sometimes single .tex files (not
    # actually tars) or gzipped tex files. Try tar first, then fall
    # back to copying raw.
    try:
        with tarfile.open(tar_path, "r:*") as tar:
            members = tar.getmembers()
            for m in members:
                mpath = (dest_dir / m.name).resolve()
                if not str(mpath).startswith(str(dest_dir.resolve())):
                    raise RuntimeError(
                        f"refusing unsafe tar member path: {m.name}"
                    )
            tar.extractall(dest_dir)
        return
    except tarfile.ReadError:
        pass
    # Not a tar. Could be a plain .tex or a gzipped .tex.
    # Try gzip-to-tex.
    import gzip

    try:
        with gzip.open(tar_path, "rb") as gz:
            data = gz.read()
        (dest_dir / "main.tex").write_bytes(data)
        return
    except OSError:
        pass
    # Last resort: copy raw.
    shutil.copy2(tar_path, dest_dir / "main.tex")


def write_sentinel(paper_dir: Path, meta: dict) -> None:
    sentinel = paper_dir / ".fetched"
    sentinel.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "id": meta["id"],
                "version": meta["version"],
                "sha256": meta["sha256"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def already_fetched(paper_dir: Path, expected_sha: str) -> bool:
    sentinel = paper_dir / ".fetched"
    if not sentinel.exists():
        return False
    try:
        data = json.loads(sentinel.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return data.get("sha256") == expected_sha


# --- Actions -----------------------------------------------------------


def action_list(manifest: dict) -> int:
    print("codependent.sty real-world corpus manifest")
    print("=" * 60)
    papers = manifest.get("papers", [])
    for p in papers:
        print(f"  {p['id']}{p['version']:4} [{p['category']:9}] {p['title']}")
        print(f"     sha256: {p['sha256']}")
        print(f"     notes : {p['notes']}")
        print()
    print(f"Total: {len(papers)} papers")
    return 0


def action_clean() -> int:
    if not PAPERS_DIR.exists():
        log("papers/ does not exist; nothing to clean.")
        return 0
    # Confirm prompt.
    try:
        reply = input(f"Remove {PAPERS_DIR} and all contents? [y/N] ")
    except EOFError:
        reply = ""
    if reply.strip().lower() != "y":
        log("Aborted.")
        return 1
    shutil.rmtree(PAPERS_DIR)
    log(f"Removed {PAPERS_DIR}.")
    return 0


def fetch_one(
    paper: dict,
    accept_pending: bool,
    last_request_time: list[float],
) -> bool:
    """Fetch and verify one paper. Returns True on success."""
    pid = paper["id"]
    ver = paper["version"]
    expected_sha = paper["sha256"]
    paper_dir = PAPERS_DIR / pid

    if expected_sha == "PENDING_FETCH" and not accept_pending:
        log(
            f"ERROR: paper {pid}{ver} has sha256=PENDING_FETCH.\n"
            f"  This manifest has not been populated with a real sha yet.\n"
            f"  To compute it for the first time, run:\n"
            f"      python fetch.py --accept-pending {pid}\n"
            f"  The observed sha will be printed to stderr. Copy it\n"
            f"  into corpus.lock (replacing PENDING_FETCH) and rerun\n"
            f"  `python fetch.py` to verify."
        )
        return False

    if already_fetched(paper_dir, expected_sha):
        log(f"[skip] {pid}{ver} already fetched (sha matches).")
        return True

    # Rate limit.
    if last_request_time:
        gap = time.monotonic() - last_request_time[0]
        if gap < REQUEST_GAP_SECONDS:
            time.sleep(REQUEST_GAP_SECONDS - gap)

    url = arxiv_url(pid, ver)
    log(f"[fetch] {pid}{ver} <- {url}")

    # Download to a temp file under PAPERS_DIR.
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = PAPERS_DIR / f".{pid}.tmp"
    try:
        download(url, tmp_path)
    except Exception as e:
        log(f"[fail] {pid}{ver}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        last_request_time[:] = [time.monotonic()]
        return False
    last_request_time[:] = [time.monotonic()]

    observed_sha = sha256_of(tmp_path)
    log(f"[sha ] {pid}{ver}: {observed_sha}")

    if expected_sha == "PENDING_FETCH":
        log(
            f"[note] {pid}{ver}: observed sha256 = {observed_sha}\n"
            f"       Add this to corpus.lock to pin the paper."
        )
        # Proceed with extraction since user passed --accept-pending.
        effective_sha = observed_sha
    else:
        if observed_sha != expected_sha:
            log(
                f"[fail] {pid}{ver}: sha mismatch\n"
                f"       expected: {expected_sha}\n"
                f"       observed: {observed_sha}"
            )
            tmp_path.unlink()
            return False
        effective_sha = expected_sha

    # Clear any stale extracted contents, then extract.
    if paper_dir.exists():
        shutil.rmtree(paper_dir)
    paper_dir.mkdir(parents=True)

    try:
        safe_extract(tmp_path, paper_dir)
    except Exception as e:
        log(f"[fail] {pid}{ver}: extraction failed: {e}")
        tmp_path.unlink()
        return False

    tmp_path.unlink()

    write_sentinel(
        paper_dir,
        {"id": pid, "version": ver, "sha256": effective_sha},
    )
    log(f"[ ok ] {pid}{ver} extracted to {paper_dir}")
    return True


def action_fetch(
    manifest: dict, ids: list[str], accept_pending: bool
) -> int:
    papers = manifest.get("papers", [])
    if ids:
        papers = [p for p in papers if p["id"] in ids]
        if not papers:
            log(f"ERROR: no manifest entries match ids={ids}")
            return 2
    if not papers:
        log("ERROR: manifest has no papers")
        return 2

    last_request_time: list[float] = []
    failures = 0
    for p in papers:
        ok = fetch_one(p, accept_pending, last_request_time)
        if not ok:
            failures += 1

    if failures:
        log(f"\n{failures} of {len(papers)} papers failed.")
        return 1
    log(f"\nAll {len(papers)} papers fetched successfully.")
    return 0


# --- Entry point -------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="fetch.py",
        description="Fetch arxiv source tarballs for codependent.sty "
        "real-world integration testing.",
    )
    ap.add_argument(
        "ids",
        nargs="*",
        help="Optional list of arxiv IDs to fetch. Default: all in manifest.",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="Print manifest contents and exit without downloading.",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="Remove papers/ directory (with confirmation prompt).",
    )
    ap.add_argument(
        "--accept-pending",
        action="store_true",
        help="Allow fetching papers whose sha256 is PENDING_FETCH. "
        "Prints the observed sha to stderr for manual population.",
    )
    args = ap.parse_args(argv)

    if args.clean:
        return action_clean()

    manifest = load_manifest()

    if args.list:
        return action_list(manifest)

    return action_fetch(manifest, args.ids, args.accept_pending)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
