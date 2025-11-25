#!/usr/bin/env python3
"""Cache remote images into the local assets folder.

This script finds any references to supported remote asset hosts inside HTML
files, downloads a copy (mirroring the original folder structure under
./assets), and updates the HTML files so that the references point at the
downloaded copies.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Set, Tuple

ASSET_HOSTS = ("assets.rmb.co.za", "cdn-assets-eu.frontify.com")
URL_PATTERN = re.compile(
    r"https://(?:assets\.rmb\.co\.za|cdn-assets-eu\.frontify\.com)/[^\s\"'()<>]+"
)


class MissingRemoteAsset(RuntimeError):
    """Raised when a remote asset responds with 404 and should be skipped."""



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

    parsed = urllib.parse.urlparse(url)
    # Build a small set of request variants to handle Frontify's picky URL
    # encoding. Primary attempt keeps ":" intact; fallback encodes them; final
    # attempt drops query params (some resized assets error with query strings).
    path_variants = [
        urllib.parse.quote(parsed.path, safe="/:"),
    ]
    if ":" in parsed.path:
        path_variants.append(urllib.parse.quote(parsed.path, safe="/"))
    if parsed.query:
        path_variants.append(urllib.parse.quote(parsed.path, safe="/:"))

    last_exc: Exception | None = None
    for idx, path_variant in enumerate(path_variants):
        candidate = parsed._replace(path=path_variant)
        if idx == len(path_variants) - 1 and parsed.query:
            candidate = candidate._replace(query="")

        encoded_url = urllib.parse.urlunparse(candidate)
        request = urllib.request.Request(
            encoded_url, headers={"User-Agent": "Mozilla/5.0"}
        )
        try:
            with urllib.request.urlopen(request) as response, destination.open(
                "wb"
            ) as fh:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    fh.write(chunk)
            return True
        except urllib.error.HTTPError as exc:  # pragma: no cover - network failure path
            if exc.code == 404:
                raise MissingRemoteAsset(url) from exc
            last_exc = exc
            continue
        except urllib.error.URLError as exc:  # pragma: no cover - network failure path
            last_exc = exc
            continue

    raise RuntimeError(f"Failed to download {url}: {last_exc}") from last_exc

    return True


def rewrite_file(
    file_path: pathlib.Path,
    project_root: pathlib.Path,
    seen_urls: Set[str],
    force_download: bool,
    dry_run: bool,
    missing_assets: List[Tuple[pathlib.Path, str]],
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
        if parsed.netloc not in ASSET_HOSTS:
            continue

        remote_path = parsed.path.lstrip("/")
        if not remote_path:
            continue

        # Preserve the directory structure under ./assets/<remote_path>
        local_relative = pathlib.Path("assets") / pathlib.Path(remote_path)
        local_full_path = project_root / local_relative

        if not dry_run and url not in seen_urls:
            try:
                download_remote_file(url, local_full_path, force_download)
            except MissingRemoteAsset:
                missing_assets.append((file_path, url))
                continue
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
    missing_assets: List[Tuple[pathlib.Path, str]] = []
    html_files = sorted(find_html_files(root))

    total_files = 0
    total_assets = 0
    rewritten_files = 0

    for html_file in html_files:
        changed, count = rewrite_file(
            html_file, root, seen_urls, force_download, dry_run, missing_assets
        )
        if count:
            total_files += 1
            total_assets += count
            if changed:
                rewritten_files += 1
                print(f"Updated {html_file.relative_to(root)} ({count} assets)")
            elif dry_run:
                print(f"Would update {html_file.relative_to(root)} ({count} assets)")

    if not total_assets:
        print("No remote assets found.")
        return

    verb = "Would cache" if dry_run else "Cached"
    print(
        f"{verb} {total_assets} asset(s) referenced across {total_files} HTML file(s). "
        f"Rewrote {rewritten_files} file(s)."
    )

    if missing_assets and not dry_run:
        print("\nSkipped missing assets (HTTP 404):")
        for page_path, url in missing_assets:
            print(f"- {page_path.relative_to(root)}: {url}")


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
