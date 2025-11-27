#!/usr/bin/env python3
"""List <img> tags referencing image paths that resolve to .webp files."""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
SRC_RE = re.compile(r"src\s*=\s*(\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.IGNORECASE)


def find_html_files(root: str) -> Iterable[str]:
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith(".html"):
                yield os.path.join(dirpath, name)


def is_webp(path: str) -> bool:
    if not path:
        return False
    trimmed = path.split("?", 1)[0].split("#", 1)[0]
    return trimmed.lower().endswith(".webp")


def find_webp_tags(html_path: str) -> List[Tuple[int, str, str]]:
    results: List[Tuple[int, str, str]] = []
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    for match in IMG_TAG_RE.finditer(content):
        tag_text = match.group(0)
        src_match = SRC_RE.search(tag_text)
        if not src_match:
            continue
        # src groups: entire match and three capture groups for quoted/unquoted values
        src_value = next((g for g in src_match.groups()[1:] if g), "")
        if is_webp(src_value):
            line_no = content.count("\n", 0, match.start()) + 1
            results.append((line_no, src_value, tag_text.strip()))
    return results


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    hits = 0
    for html_path in sorted(find_html_files(root)):
        tags = find_webp_tags(html_path)
        if not tags:
            continue
        rel_path = os.path.relpath(html_path, root)
        print(rel_path)
        for line_no, src_value, tag_text in tags:
            print(f"  line {line_no}: src='{src_value}' -> {tag_text}")
            hits += 1
    if hits == 0:
        print("No <img> tags pointing to .webp files were found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
