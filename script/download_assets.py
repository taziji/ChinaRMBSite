#!/usr/bin/env python3
"""
Download image assets referenced by an RMB HTML page and rewire the page to use the local copies.
By default assets mirror their remote folder structure beneath ``assets/`` (for example,
``https://assets.rmb.co.za/images/content/about/logo.png`` becomes
``assets/images/content/about/logo.png``).

Example:
    python download_assets.py \
        http://127.0.0.1:8080/rmbcibusa.com_solutions-corporate-finance-advisory.html

Dependencies:
    pip install -r script/requirements.txt
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[1]
CHINARMBSITE_ROOT = REPO_ROOT / "ChinaRMBSite"
DEFAULT_OUTPUT_DIR = CHINARMBSITE_ROOT / "assets"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0 Safari/537.36"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download <img> assets from an RMB page and update the local HTML file to point to them."
    )
    parser.add_argument(
        "url",
        help="URL of the rendered page (e.g. http://127.0.0.1:8080/page.html). "
        "Relative asset URLs will be resolved against this address.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=(
            "Root directory to save downloaded assets. "
            f"Defaults to {DEFAULT_OUTPUT_DIR}; remote paths are mirrored beneath it."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite asset files if they already exist.",
    )
    parser.add_argument(
        "--html-file",
        help=(
            "Path to the local HTML file that should be rewired. "
            "If omitted, the script attempts to infer it from the URL path under ChinaRMBSite/."
        ),
    )
    return parser.parse_args()


def fetch_page(url: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def gather_image_sources(html: str) -> Iterable[str]:
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        yield src.strip()


def sanitize_filename(raw_name: str) -> str:
    name = raw_name.split("?")[0].split("#")[0]
    name = unquote(name)
    if not name or name.endswith("/"):
        name = name.rstrip("/")
        if not name:
            name = "image"
    base = Path(name).name
    if not base:
        base = "image"
    safe = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in base)
    return safe or hashlib.md5(raw_name.encode("utf-8")).hexdigest()


def build_relative_asset_path(raw_path: str) -> Path:
    cleaned = raw_path.split("?")[0].split("#")[0]
    cleaned = unquote(cleaned)
    parts = [part for part in cleaned.split("/") if part]
    if not parts:
        parts = ["image"]

    # If the remote path contains "assets" deeper in the directory tree, drop the
    # leading segments so downloaded files live beneath the local assets root.
    try:
        assets_index = next(
            index for index, part in enumerate(parts[:-1]) if part.lower() == "assets"
        )
    except StopIteration:
        assets_index = None
    if assets_index and assets_index > 0:
        parts = parts[assets_index:]

    directories = []
    for index, part in enumerate(parts[:-1]):
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in part)
        if not safe:
            safe = f"dir_{index}"
        directories.append(safe)

    filename = sanitize_filename(parts[-1])
    return Path(*directories, filename)


def infer_extension(content_type: str, destination: Path) -> Optional[str]:
    content_type = content_type.split(";")[0].strip().lower()
    if destination.suffix:
        return destination.suffix
    if content_type == "image/svg+xml":
        return ".svg"
    if content_type == "image/png":
        return ".png"
    if content_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if content_type == "image/gif":
        return ".gif"
    if content_type == "image/webp":
        return ".webp"
    if content_type == "image/avif":
        return ".avif"
    return None


def download_asset(
    asset_url: str, destination: Path, overwrite: bool
) -> Optional[Tuple[Path, bool]]:
    headers = {"User-Agent": USER_AGENT}

    response = requests.get(asset_url, headers=headers, timeout=30, stream=True)
    response.raise_for_status()

    ext = infer_extension(response.headers.get("Content-Type", ""), destination)
    final_destination = destination.with_suffix(ext) if ext else destination

    if final_destination.exists() and not overwrite:
        rel = final_destination.relative_to(REPO_ROOT)
        print(f"[skip] {asset_url} (exists at {rel})")
        return final_destination, False

    final_destination.parent.mkdir(parents=True, exist_ok=True)
    with final_destination.open("wb") as file_handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file_handle.write(chunk)

    rel = final_destination.relative_to(REPO_ROOT)
    print(f"[ok]   {asset_url} -> {rel}")
    return final_destination, True


def resolve_assets(
    page_url: str,
    sources: Iterable[str],
    output_dir: Path,
    overwrite: bool,
) -> Tuple[Dict[str, Path], int, int]:
    downloaded = 0
    skipped = 0
    mapping: Dict[str, Path] = {}
    seen: Dict[str, Path] = {}

    for src in sources:
        asset_url = urljoin(page_url, src)
        parsed = urlparse(asset_url)
        if not parsed.scheme.startswith("http"):
            print(f"[warn] Unsupported scheme for {asset_url}, skipping.")
            skipped += 1
            continue

        relative_path = build_relative_asset_path(parsed.path or parsed.netloc)

        output_root = output_dir.name
        if (
            output_root
            and output_root not in {".", os.sep}
            and len(relative_path.parts) > 1
            and relative_path.parts[0].lower() == output_root.lower()
        ):
            relative_path = Path(*relative_path.parts[1:])

        destination = (output_dir / relative_path).resolve()

        if asset_url in seen and not overwrite:
            print(f"[skip] {asset_url} (already downloaded as {seen[asset_url]})")
            skipped += 1
            continue

        try:
            outcome = download_asset(asset_url, destination, overwrite=overwrite)
            if outcome is None:
                skipped += 1
                continue
            final_destination, was_downloaded = outcome
            if was_downloaded:
                downloaded += 1
            else:
                skipped += 1
            seen[asset_url] = final_destination.relative_to(REPO_ROOT)
            mapping[asset_url] = final_destination
        except requests.HTTPError as err:
            print(f"[fail] HTTP error {err.response.status_code} for {asset_url}")
            skipped += 1
        except requests.RequestException as err:
            print(f"[fail] Request error for {asset_url}: {err}")
            skipped += 1

    return mapping, downloaded, skipped


def infer_html_path_from_url(url: str) -> Path | None:
    parsed = urlparse(url)
    if not parsed.path:
        return None
    candidate = CHINARMBSITE_ROOT / parsed.path.lstrip("/")
    if candidate.is_file():
        return candidate
    return None


def wire_assets_into_html(
    html_file: Path, page_url: str, asset_map: Dict[str, Path]
) -> None:
    if not html_file.is_file():
        print(f"[warn] HTML file not found: {html_file}")
        return

    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
    updated = False

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        resolved = urljoin(page_url, src.strip())
        local_path = asset_map.get(resolved)
        if not local_path:
            continue

        try:
            web_path = "/" + local_path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            web_path = os.path.relpath(local_path, html_file.parent).replace(os.sep, "/")

        if img["src"] != web_path:
            img["src"] = web_path
            updated = True

    if updated:
        html_file.write_text(soup.decode(), encoding="utf-8")
        print(f"[wire] Updated image sources in {html_file.relative_to(REPO_ROOT)}")
    else:
        print(f"[wire] No image sources updated for {html_file.relative_to(REPO_ROOT)}")


def main() -> int:
    args = parse_arguments()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        html = fetch_page(args.url)
    except requests.RequestException as err:
        print(f"Failed to fetch page: {err}")
        return 1

    sources = list(gather_image_sources(html))
    if not sources:
        print("No <img> tags found on the page.")
        return 0

    print(f"Found {len(sources)} image references. Downloading to {output_dir}.")
    asset_map, downloaded, skipped = resolve_assets(
        args.url, sources, output_dir, args.overwrite
    )
    print(f"\nCompleted downloads. Downloaded: {downloaded}, Skipped/Failed: {skipped}")

    html_path: Path | None
    if args.html_file:
        html_path = Path(args.html_file).expanduser()
    else:
        html_path = infer_html_path_from_url(args.url)
        if html_path:
            print(f"Inferred HTML file: {html_path.relative_to(REPO_ROOT)}")

    if html_path and asset_map:
        wire_assets_into_html(html_path, args.url, asset_map)
    elif not html_path:
        print("No HTML file specified or inferred; skipping rewiring step.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
