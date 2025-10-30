#!/usr/bin/env python3
"""
Batch download image assets for every HTML page in the repository.

For each *.html file under the chosen root directory the script:
    1. Fetches the rendered page from a locally served base URL.
    2. Downloads all referenced <img> assets into the local assets directory.
    3. Rewrites the HTML file so the <img src> attributes point at the local copies.

Example:
    python batch_download_assets.py \
        --base-url http://127.0.0.1:8083/ \
        --html-root . \
        --output-dir assets
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urljoin

import requests

from download_assets import (
    REPO_ROOT,
    fetch_page,
    gather_image_sources,
    resolve_assets,
    wire_assets_into_html,
)


DEFAULT_BASE_URL = "http://127.0.0.1:8083/"
DEFAULT_HTML_ROOT = REPO_ROOT
DEFAULT_OUTPUT_DIR = REPO_ROOT / "assets"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch download <img> assets for every HTML page beneath a root directory."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "Base URL that serves the HTML files (defaults to http://127.0.0.1:8083/). "
            "Each HTML file's repository-relative path is appended to this base."
        ),
    )
    parser.add_argument(
        "--html-root",
        type=Path,
        default=DEFAULT_HTML_ROOT,
        help="Directory containing the HTML files to process (defaults to the repository root).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to store downloaded assets (defaults to ./assets).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite asset files if they already exist.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "Optional paths (files or directories) relative to --html-root to limit processing. "
            "If omitted, every HTML file under --html-root is processed."
        ),
    )
    return parser.parse_args()


def iter_html_files(root: Path, selection: Iterable[str]) -> List[Path]:
    if selection:
        candidates = []
        for raw in selection:
            target = (root / raw).resolve()
            if target.is_file() and target.suffix.lower() == ".html":
                candidates.append(target)
            elif target.is_dir():
                candidates.extend(sorted(target.rglob("*.html")))
            else:
                print(f"[warn] Skipping unknown path: {raw}")
        html_files = candidates
    else:
        html_files = sorted(root.rglob("*.html"))

    filtered: List[Path] = []
    for html_file in html_files:
        try:
            relative = html_file.relative_to(root.resolve())
        except ValueError:
            # If the file sits outside the root (e.g. due to symlink resolution) skip it.
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        if "assets" in relative.parts:
            continue
        if html_file.is_file():
            filtered.append(html_file)
    return filtered


def build_page_url(base_url: str, relative_path: Path) -> str:
    base = base_url.rstrip("/") + "/"
    return urljoin(base, relative_path.as_posix())


def process_html_file(
    html_file: Path,
    root: Path,
    base_url: str,
    output_dir: Path,
    overwrite: bool,
) -> None:
    relative = html_file.relative_to(root)
    page_url = build_page_url(base_url, relative)

    try:
        html = fetch_page(page_url)
    except requests.RequestException as err:
        print(f"[error] Failed to fetch {page_url}: {err}")
        return

    sources = list(gather_image_sources(html))
    if not sources:
        print(f"[skip] {relative} (no <img> tags)")
        return

    print(f"\n[page] {relative} ({len(sources)} image references)")
    asset_map, downloaded, skipped = resolve_assets(
        page_url, sources, output_dir, overwrite
    )
    print(f"[page] Downloaded: {downloaded}, Skipped/Failed: {skipped}")

    if asset_map:
        wire_assets_into_html(html_file, page_url, asset_map)
    else:
        print(f"[page] No assets downloaded for {relative}")


def main() -> int:
    args = parse_arguments()
    html_root = args.html_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not html_root.is_dir():
        print(f"[error] HTML root not found: {html_root}")
        return 1

    html_files = iter_html_files(html_root, args.paths)
    if not html_files:
        print("[info] No HTML files found to process.")
        return 0

    print(f"[info] Processing {len(html_files)} HTML files found under {html_root}")
    for html_file in html_files:
        process_html_file(
            html_file,
            html_root,
            args.base_url,
            output_dir,
            args.overwrite,
        )

    print("\n[done] Batch asset download complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
