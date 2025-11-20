#!/usr/bin/env python3
"""Cache images hosted under https://assets.rmb.co.za into the local assets folder.

This script finds any references to the remote asset host inside HTML files,
downloads a copy (mirroring the original folder structure under ./assets), and
updates the HTML files so that the references point at the downloaded copies.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterable, Set, Tuple

ASSET_HOST = "assets.rmb.co.za"
ASSET_BASE_URL = f"https://{ASSET_HOST}"
URL_PATTERN = re.compile(r"https://assets\.rmb\.co\.za/[^\s\"'()<>]+")


def find_html_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    """Yield every HTML file under the provided root directory."""
    for path in root.glob("**/*.html"):
        if path.is_file():
            yield path


def download_remote_file(url: str, destination: pathlib.Path, force: bool) -> bool:
    """Download ``url`` into ``destination``.

    Returns True if the file was downloaded (or overwritten) and False if the file
    already existed and ``force`` is False. Any download errors are surfaced to the
    caller with a helpful message.
    """
    if destination.exists() and not force:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request) as response, destination.open("wb") as fh:
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                fh.write(chunk)
    except urllib.error.URLError as exc:  # pragma: no cover - network failure path
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc

    return True


def rewrite_file(
    file_path: pathlib.Path,
    project_root: pathlib.Path,
    seen_urls: Set[str],
    force_download: bool,
    dry_run: bool,
) -> Tuple[bool, int]:
    """Download any remote assets in ``file_path`` and rewrite the HTML.

    Returns ``(changed, count)`` where ``changed`` indicates whether the HTML file
    was rewritten and ``count`` is the number of unique remote URLs handled.
    """
    original_text = file_path.read_text(encoding="utf-8")
    matches = set(URL_PATTERN.findall(original_text))
    if not matches:
        return False, 0

    replacements: Dict[str, str] = {}
    for url in matches:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc != ASSET_HOST:
            continue

        remote_path = parsed.path.lstrip("/")
        if not remote_path:
            continue

        # Preserve the directory structure under ./assets/<remote_path>
        local_relative = pathlib.Path("assets") / pathlib.Path(remote_path)
        local_full_path = project_root / local_relative

        if not dry_run and url not in seen_urls:
            download_remote_file(url, local_full_path, force_download)
            seen_urls.add(url)

        replacements[url] = "/" + local_relative.as_posix()

    new_text = original_text
    for remote_url, local_url in replacements.items():
        new_text = new_text.replace(remote_url, local_url)

    if dry_run or new_text == original_text:
        return False, len(replacements)

    file_path.write_text(new_text, encoding="utf-8")
    return True, len(replacements)


def run(root: pathlib.Path, dry_run: bool, force_download: bool) -> None:
    if not root.exists():
        raise SystemExit(f"Root path {root} not found")

    seen_urls: Set[str] = set()
    html_files = sorted(find_html_files(root))

    total_files = 0
    total_assets = 0
    rewritten_files = 0

    for html_file in html_files:
        changed, count = rewrite_file(html_file, root, seen_urls, force_download, dry_run)
        if count:
            total_files += 1
            total_assets += count
            if changed:
                rewritten_files += 1
                print(f"Updated {html_file.relative_to(root)} ({count} assets)")
            elif dry_run:
                print(f"Would update {html_file.relative_to(root)} ({count} assets)")

    if not total_assets:
        print("No remote RMB assets found.")
        return

    verb = "Would cache" if dry_run else "Cached"
    print(
        f"{verb} {total_assets} asset(s) referenced across {total_files} HTML file(s). "
        f"Rewrote {rewritten_files} file(s)."
    )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=pathlib.Path.cwd(),
        type=pathlib.Path,
        help="Project root that contains the assets folder (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without downloading files or rewriting HTML",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download files even if a cached copy already exists",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    run(args.root.resolve(), args.dry_run, args.force_download)


if __name__ == "__main__":
    main()
