#!/usr/bin/env python3
"""Offline checks for the GitHub profile README and ODD PRACTIC SVG assets."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "README.md", ROOT / "docs" / "PROFILE-DESIGN.md"]
ASSETS = sorted((ROOT / "assets").glob("odd-*.svg"))
errors: list[str] = []
checked_links = 0


def error(message: str) -> None:
    errors.append(message)


def target_is_local(raw: str) -> bool:
    value = raw.strip()
    return bool(value) and not (
        value.startswith(("#", "//", "mailto:", "data:"))
        or urlsplit(value).scheme
    )


def check_link(origin: Path, raw: str) -> None:
    global checked_links
    if not target_is_local(raw):
        return
    path = unquote(urlsplit(raw).path)
    if not path:
        return
    target = (origin.parent / path).resolve()
    try:
        target.relative_to(ROOT)
    except ValueError:
        error(f"{origin.relative_to(ROOT)}: path escapes repository: {raw}")
        return
    checked_links += 1
    if not target.is_file():
        error(f"{origin.relative_to(ROOT)}: missing local file: {raw}")


def anchors(text: str) -> set[str]:
    slugs: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(1)).lower().strip()
        title = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
        title = re.sub(r"\s+", "-", title)
        slug = title
        index = 1
        while slug in slugs:
            slug = f"{title}-{index}"
            index += 1
        slugs.add(slug)
    return slugs


def check_markdown(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found_anchors = anchors(text)
    for raw in re.findall(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]+\")?\)", text):
        if raw.startswith("#"):
            if raw[1:] not in found_anchors:
                error(f"{path.relative_to(ROOT)}: unknown anchor: {raw}")
        else:
            check_link(path, raw)
    for raw in re.findall(r"\b(?:src|srcset|href)\s*=\s*['\"]([^'\"]+)['\"]", text):
        for src in raw.split(","):
            check_link(path, src.strip().split()[0])
    if text.count("<details>") != text.count("</details>"):
        error(f"{path.relative_to(ROOT)}: unbalanced details")
    if text.count("<summary>") != text.count("</summary>"):
        error(f"{path.relative_to(ROOT)}: unbalanced summary")
    for image in re.findall(r"<img\b[^>]*>", text):
        if not re.search(r"\balt\s*=\s*['\"][^'\"]+['\"]", image):
            error(f"{path.relative_to(ROOT)}: image lacks meaningful alt text")
    for alt in re.findall(r"!\[([^\]]*)\]\(", text):
        if not alt.strip():
            error(f"{path.relative_to(ROOT)}: Markdown image lacks alt text")


def check_svg(path: Path) -> None:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        error(f"{path.relative_to(ROOT)}: invalid SVG XML: {exc}")
        return
    root = tree.getroot()
    if root.tag != "{http://www.w3.org/2000/svg}svg" or "viewBox" not in root.attrib:
        error(f"{path.relative_to(ROOT)}: missing SVG namespace or viewBox")
    if not root.find("{http://www.w3.org/2000/svg}title") is not None:
        error(f"{path.relative_to(ROOT)}: missing title element")
    if not root.find("{http://www.w3.org/2000/svg}desc") is not None:
        error(f"{path.relative_to(ROOT)}: missing desc element")

    body = path.read_text(encoding="utf-8")
    blocked = ("<script", "<foreignObject", "javascript:", "@import", "url(http")
    if any(fragment.lower() in body.lower() for fragment in blocked):
        error(f"{path.relative_to(ROOT)}: forbidden executable or remote SVG content")
    for element in tree.iter():
        for key, value in element.attrib.items():
            name = key.rsplit("}", 1)[-1]
            if name.startswith("on") or (name in ("href", "src") and urlsplit(value).scheme):
                error(f"{path.relative_to(ROOT)}: unsafe attribute: {name}")
    style = "\n".join((node.text or "") for node in tree.iter() if node.tag.endswith("}style"))
    if style.count("{") != style.count("}"):
        error(f"{path.relative_to(ROOT)}: unbalanced CSS braces")
    if ("animation:" in style or "@keyframes" in style) and "prefers-reduced-motion" not in style:
        error(f"{path.relative_to(ROOT)}: missing reduced-motion fallback")


def main() -> int:
    for path in FILES:
        if not path.is_file():
            error(f"Missing Markdown file: {path}")
        else:
            check_markdown(path)
    if len(ASSETS) < 5:
        error("Expected at least five ODD SVG assets")
    for path in ASSETS:
        check_svg(path)
    if errors:
        print("Profile QA FAILED")
        for item in errors:
            print(" -", item)
        return 1
    print(f"Profile QA PASS: {len(FILES)} Markdown files, {len(ASSETS)} SVG assets, {checked_links} local references.")
    print("Visual rendering, remote URLs and GitHub theme behavior still require manual review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
