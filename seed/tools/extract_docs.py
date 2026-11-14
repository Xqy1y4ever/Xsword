"""从 .docx / 旧版 .doc 中提取文本（零依赖：docx 用 zipfile，doc 用 olefile + piece table）。

用法（在 src/ 下执行）：
  python seed/tools/extract_docs.py "大学英语通用词汇.doc" --limit 80
  python seed/tools/extract_docs.py "Vocabulary 10.11.docx" --limit 200
"""
from __future__ import annotations

import argparse
import struct
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
CELL_MARK = "\x07"
PARA_MARK = "\r"


def _text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iterfind(".//w:t", NS)).strip()


def extract_docx(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find("w:body", NS)
    lines: list[str] = []
    if body is None:
        return lines
    for child in body:
        tag = child.tag.split("}")[1]
        if tag == "p":
            value = _text_of(child)
            if value:
                lines.append(value)
        elif tag == "tbl":
            for row in child.iterfind("w:tr", NS):
                cells = [_text_of(cell) for cell in row.iterfind("w:tc", NS)]
                if any(cells):
                    lines.append(" | ".join(cells))
    return lines


def _extract_doc_stream(path: Path) -> str:
    import olefile

    ole = olefile.OleFileIO(str(path))
    try:
        word = ole.openstream("WordDocument").read()
        flags = struct.unpack_from("<H", word, 0x0A)[0]
        table_name = "1Table" if (flags & 0x0200) else "0Table"
        if not ole.exists(table_name):
            table_name = "1Table" if ole.exists("1Table") else "0Table"
        table = ole.openstream(table_name).read()
        fc_clx, lcb_clx = struct.unpack_from("<II", word, 0x01A2)
        clx = table[fc_clx : fc_clx + lcb_clx]
        # CLX = 若干 Prc(0x01) + 一个 Pcdt(0x02)
        index = 0
        plc = b""
        while index < len(clx):
            kind = clx[index]
            if kind == 0x01:
                size = struct.unpack_from("<H", clx, index + 1)[0]
                index += 3 + size
            elif kind == 0x02:
                size = struct.unpack_from("<I", clx, index + 1)[0]
                plc = clx[index + 5 : index + 5 + size]
                break
            else:
                break
        if not plc:
            raise ValueError("未找到 piece table")
        count = (len(plc) - 4) // 12
        cps = [struct.unpack_from("<i", plc, 4 * k)[0] for k in range(count + 1)]
        pieces = []
        for k in range(count):
            raw_fc = struct.unpack_from("<I", plc, 4 * (count + 1) + 8 * k + 2)[0]
            compressed = bool(raw_fc & 0x40000000)
            fc = raw_fc & 0x3FFFFFFF
            chars = cps[k + 1] - cps[k]
            if chars <= 0:
                continue
            if compressed:
                fc //= 2
                pieces.append(word[fc : fc + chars].decode("cp1252", errors="replace"))
            else:
                pieces.append(word[fc : fc + chars * 2].decode("utf-16-le", errors="replace"))
        return "".join(pieces)
    finally:
        ole.close()


def extract_doc(path: Path) -> list[str]:
    text = _extract_doc_stream(path)
    text = text.replace(CELL_MARK, "\t").replace("\x0b", " ").replace("\x0c", "\n")
    lines = []
    for raw in text.replace(PARA_MARK, "\n").split("\n"):
        value = raw.strip()
        if value:
            lines.append(value)
    return lines


def extract(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".doc":
        return extract_doc(path)
    raise ValueError(f"不支持的文件类型：{suffix}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提取 Word 文本")
    parser.add_argument("path", type=Path)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--raw", action="store_true", help="用 repr 打印，便于看分隔符")
    args = parser.parse_args(argv)

    lines = extract(args.path)
    print(f"# {args.path.name}: {len(lines)} 行", file=sys.stderr)
    for index, line in enumerate(lines[: args.limit]):
        print(f"{index:04d} {repr(line) if args.raw else line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
