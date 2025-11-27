#!/usr/bin/env python3
"""Extract HTML file paths and image src values from img_issues.txt output."""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, Tuple

LINE_RE = re.compile(r"src=['\"]([^'\"]+)['\"]")


def parse_issue_file(path: str) -> Iterable[Tuple[str, str]]:
    current_file = None
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            if not line or not line[0].isspace():
                current_file = line.strip()
                continue
            if current_file is None:
                continue
            match = LINE_RE.search(line)
            if match:
                yield current_file, match.group(1)


def main() -> int:
    issue_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "img_issues.txt"
    )
    if not os.path.exists(issue_file):
        print(f"Issue file not found: {issue_file}", file=sys.stderr)
        return 1
    html_files = set()
    src_paths = set()
    for html_path, img_src in parse_issue_file(issue_file):
        html_files.add(html_path)
        src_paths.add(img_src)

    if not html_files:
        print("No image issues found in the provided file.")
        return 0

    print("HTML files with image issues:")
    for path in sorted(html_files):
        print(path)

    print("\nImage paths referenced without extensions:")
    for src in sorted(src_paths):
        print(src)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
