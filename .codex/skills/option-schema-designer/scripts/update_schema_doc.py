from __future__ import annotations

import argparse
import os
from pathlib import Path
import re


SECTION_HEADING = "## E-R 图"
START_MARKER = "<!-- option-schema-designer:er-diagram:start -->"
END_MARKER = "<!-- option-schema-designer:er-diagram:end -->"


def build_diagram_block(doc_path: Path, image_path: Path, title: str) -> str:
    relative_str = Path(os.path.relpath(image_path, doc_path.parent).replace("\\", "/"))
    return "\n".join(
        [
            START_MARKER,
            f"![{title}]({relative_str.as_posix()})",
            END_MARKER,
        ]
    )


def update_schema_doc(doc_path: Path, image_path: Path, title: str) -> Path:
    doc_path = doc_path.expanduser().resolve()
    image_path = image_path.expanduser().resolve()
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    if not doc_path.exists():
        doc_path.write_text("", encoding="utf-8")

    content = doc_path.read_text(encoding="utf-8")
    block = build_diagram_block(doc_path, image_path, title)

    marker_pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    if marker_pattern.search(content):
        updated = marker_pattern.sub(block, content, count=1)
    elif SECTION_HEADING in content:
        updated = content.replace(
            SECTION_HEADING,
            f"{SECTION_HEADING}\n\n{block}",
            1,
        )
    else:
        trimmed = content.rstrip()
        prefix = f"{trimmed}\n\n" if trimmed else ""
        updated = f"{prefix}{SECTION_HEADING}\n\n{block}\n"

    if not updated.endswith("\n"):
        updated += "\n"
    doc_path.write_text(updated, encoding="utf-8")
    return doc_path


def main() -> int:
    parser = argparse.ArgumentParser(description="将渲染后的 E-R 图插入 schema 文档。")
    parser.add_argument("--doc", required=True, type=Path, help="Schema Markdown 路径")
    parser.add_argument("--image", required=True, type=Path, help="SVG 图片路径")
    parser.add_argument("--title", required=True, help="Markdown 图片标题")
    args = parser.parse_args()

    update_schema_doc(doc_path=args.doc, image_path=args.image, title=args.title)
    print(args.doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
