"""从笔记/Word 词表/《大学英语通用词汇》提取词条，去重后生成种子文件。

用法（在 src/ 下执行）：
  python seed/tools/build_wordlist.py

输出：
  seed/nce_a.json        南京大学《大学英语通用词汇》A 级词（自带释义）
  seed/_candidates.json  来自笔记与 Word 词表、需要补中文释义的新词
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

from extract_docs import extract

ROOT = Path(__file__).resolve().parents[2]          # src/
WORKSPACE = ROOT.parent                              # 项目根（笔记与 word 文件所在处）
SEED = ROOT / "seed"
DB_PATH = ROOT / "data" / "app.db"

DOCX_FILES = [
    "10.21.docx",
    "10.28.docx",
    "unit 1-4 essentials.docx",
    "Vocabulary 10.11.docx",
]
MD_FILES = [
    "9.19.md",
    "9.23 note.md",
    "9.30 note.md",
    "10.10 note.md",
    "10.14 note.md",
    "10.21 note.md",
    "10.28 note.md",
]
DOC_LEVEL_FILE = "大学英语通用词汇.doc"

TERM_RE = re.compile(r"^[a-z][a-z'\- ]{0,40}$")
SKIP_PHRASES = {
    "game of throne",
    "game of thrones",
    "black mirror",
    "stranger things",
    "breaking bad",
    "word count",
    "data clerk",
    "byte dance",
}
SKIP_TERMS = {
    "a",
    "i",
    "it",
    "is",
    "of",
    "on",
    "in",
    "to",
    "and",
    "the",
    "tb",
    "kb",
    "about",
    "bad",
    "many",
    "a-",
    "an",
    # 笔记里的拼写错误 / 重复 / 纯缩写或专名
    "inquery",
    "maturet",
    "presciption",
    "receed",
    "sustainablity",
    "aids",
    "hamas",
    "unicef",
    "paris",
    # 拆分错误的组合行
    "deceive deception",
    "pile compile",
    "valid validity",
    "one third",
    "two thirds",
    "to seize",
    "pan america",
    "mutually hated by",
    "cardio exercise activity",
    "clerk at office",
    "pharmacy store",
    "institutionalized expression",
    "large swaths of economy",
    "lack of primary education",
    "substantial amount of",
    "state based arm conflict",
    "substantial development",
    "immense stadium",
    "indulge in hatred",
}
ROOT_FRAGMENT_RE = re.compile(r"(^-|-$)")
TITLE_RE = re.compile(r"^[A-Z]")
# 专有名词保留首字母大写
CAPITALIZE = {
    "israel": "Israel",
    "israeli": "Israeli",
    "palestine": "Palestine",
    "palestinian": "Palestinian",
    "syria": "Syria",
    "yemen": "Yemen",
    "venezuela": "Venezuela",
    "pakistan": "Pakistan",
    "welsh": "Welsh",
    "cockney": "Cockney",
}


def _display_term(term: str) -> str:
    return CAPITALIZE.get(term, term)


def _normalize(term: str) -> str:
    term = term.strip().strip(".,;:!?/\\|()[]{}《》<>\"'“”‘’")
    term = term.replace("/", " ")
    term = term.replace("—", " ").replace("–", " ")
    term = re.sub(r"\s+", " ", term)
    return term.strip().lower()


def _is_usable(term: str) -> bool:
    if not term or len(term) < 3 or len(term) > 48:
        return False
    if term in SKIP_PHRASES or term in SKIP_TERMS:
        return False
    if ROOT_FRAGMENT_RE.search(term):
        return False
    if "-" in term or "'" in term:
        return False
    if not TERM_RE.match(term):
        return False
    words = term.split(" ")
    if len(words) > 4:
        return False
    return all(len(word) >= 2 for word in words)


def _split_tokens(line: str) -> list[str]:
    """一行里可能塞了多个词：用 2+ 个空格切分。"""
    parts = re.split(r"\s{2,}", line.strip())
    return [part for part in parts if part.strip()]


def parse_a_level() -> list[dict[str, str]]:
    lines = extract(WORKSPACE / DOC_LEVEL_FILE)
    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        if start is None and re.match(r"^A级词[（(]", line):
            start = index + 1
            continue
        if start is not None and re.match(r"^B级词[（(]", line):
            end = index
            break
    if start is None:
        raise SystemExit("没有在文档里找到 A 级词章节")

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in lines[start:end]:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z][A-Za-z'\- ]*?)\s+(.+)$", line)
        if not match:
            continue
        term = _normalize(match.group(1))
        meaning = match.group(2).strip()
        if not _is_usable(term) or not meaning or term in seen:
            continue
        seen.add(term)
        entries.append({"term": _display_term(term), "meaning": meaning, "tags": "nce-a"})
    return entries


def _singular_variants(term: str) -> list[str]:
    """简单的单复数变体，用来避免 "communicable diseases / disease" 这类重复。"""
    variants: list[str] = []
    if term.endswith("ies") and len(term) > 3:
        variants.append(term[:-3] + "y")
    if term.endswith("es") and len(term) > 2:
        variants.append(term[:-2])
    if term.endswith("s") and not term.endswith("ss"):
        variants.append(term[:-1])
    return variants


def _plural_variants(term: str) -> list[str]:
    if not term or term.endswith("s"):
        return []
    variants = [term + "s"]
    if term.endswith("y") and len(term) > 2:
        variants.append(term[:-1] + "ies")
    return variants


def parse_candidates(existing: set[str]) -> list[dict[str, str]]:
    candidates: dict[str, str] = {}
    known = set(existing)

    def accept(term: str, source: str) -> None:
        if not _is_usable(term):
            return
        if term in known or term in candidates:
            return
        pool = known | set(candidates)
        if any(variant in pool for variant in _singular_variants(term)):
            return
        if any(variant in pool for variant in _plural_variants(term)):
            return
        candidates[term] = source

    for name in DOCX_FILES:
        path = WORKSPACE / name
        if not path.exists():
            print(f"  ! 缺少文件 {name}", file=sys.stderr)
            continue
        for line in extract(path):
            for token in _split_tokens(line):
                accept(_normalize(token), f"word:{name}")

    for name in MD_FILES:
        path = WORKSPACE / name
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", "-", "=")):
                continue
            line = re.sub(r"\(.*?\)", " ", line)
            line = line.replace("???", " ").replace("?", " ")
            for token in re.split(r"[\t,;|]", line):
                token = token.strip()
                if not token:
                    continue
                accept(_normalize(token), f"note:{name}")
    return [{"term": term, "source": source} for term, source in sorted(candidates.items())]


def load_existing_terms() -> set[str]:
    """只用种子词表判重（导入数据库时还会再按库内单词跳过，这里不查库）。"""
    terms: set[str] = set()
    words_file = SEED / "words.json"
    if words_file.exists():
        for item in json.loads(words_file.read_text(encoding="utf-8")):
            terms.add(str(item["term"]).strip().lower())
    a_file = SEED / "nce_a.json"
    if a_file.exists():
        for item in json.loads(a_file.read_text(encoding="utf-8")):
            terms.add(str(item["term"]).strip().lower())
    return terms


def main() -> int:
    a_level = parse_a_level()
    existing = load_existing_terms()
    existing.update(item["term"] for item in a_level)
    candidates = parse_candidates(existing)

    (SEED / "nce_a.json").write_text(
        json.dumps(a_level, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # 人工补的中文释义：seed/_meanings.json
    meanings_file = SEED / "_meanings.json"
    meanings: dict[str, str] = {}
    if meanings_file.exists():
        meanings = json.loads(meanings_file.read_text(encoding="utf-8"))
    missing = [item["term"] for item in candidates if not str(meanings.get(item["term"], "")).strip()]
    if missing:
        print(f"还有 {len(missing)} 个词缺中文释义：{'、'.join(missing[:20])}", file=sys.stderr)
        return 1
    extra_entries = []
    for item in candidates:
        tag = "word-file" if item["source"].startswith("word:") else "note"
        extra_entries.append(
            {"term": _display_term(item["term"]), "meaning": meanings[item["term"]].strip(), "tags": tag}
        )
    (SEED / "words_extra.json").write_text(
        json.dumps(extra_entries, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (SEED / "_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"A 级词：{len(a_level)} 条 → seed/nce_a.json")
    print(f"笔记/Word 新词：{len(extra_entries)} 条 → seed/words_extra.json")
    unknown = sorted(set(meanings) - {item["term"] for item in candidates})
    if unknown:
        print(f"提示：_meanings.json 里有 {len(unknown)} 条没被用到：{'、'.join(unknown[:10])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
