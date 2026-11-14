"""OpenAI 兼容大模型客户端：逐一拆解单词，输出严格 JSON。"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from .llm_config import LLMConfig

PROMPT_VERSION = "v1"


class LLMNotConfigured(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


SYSTEM_PROMPT = """你是一名英语词源教学编辑，为中文母语学习者拆解英语单词。
严格只输出 JSON，不要输出任何解释文字、Markdown 或代码块标记。

输出格式：
{
  "items": [
    {
      "word": "输入里的原词，原样返回",
      "breakdown": [
        {"form": "词形片段，如 pharma", "type": "root|prefix|suffix",
         "key": "用于建索引的归一化词根/词缀，如 pharm 或 pre",
         "gloss": "该片段的中文含义", "origin": "语源，如 Greek/Latin，可空",
         "note": "补充说明，可空"}
      ],
      "mnemonic": "一句面向中文学习者的形象化记忆解释（60 字以内，说明词根词缀如何组合出词义）",
      "cognates": ["同根词，如 pharmacy"],
      "derivatives": ["该词的衍生词/屈折形式"],
      "confusables": ["易混词的简要对比如 'affront 冒犯 vs confront 面对'"]
    }
  ]
}

要求：
1. 必须优先复用用户提供的“现有词根库/词缀库”中的 key 与含义；只有确实不存在时才新增词根/词缀。
2. breakdown 中 root 是词根，prefix/suffix 是词缀，按拼写顺序排列；key 用小写、不加连字符。
3. 形如 -tion、-ment、un- 的片段放进 type=prefix/suffix，不要当成词根。
4. mnemonic 必须基于真实词源，不允许编造；不确定时写简短可靠的解释。
5. 同一批每个词都要有一条 item，顺序与输入一致。"""


POS_PROMPT = """你是一名英语词典编辑，为中文母语学习者标注英语单词的词性。
严格只输出 JSON，不要输出任何解释文字、Markdown 或代码块标记。

输出格式：
{
  "items": [
    {
      "word": "输入里的原词，原样返回",
      "pos": ["n.", "v."]
    }
  ]
}

要求：
1. 词性用常用缩写：n. v. adj. adv. prep. conj. pron. num. det. interj.；多词性按常用程度排列，最多 4 个。
2. 固定搭配/短语用 phrase.；专有名词（国家、人名等）用 proper n.。
3. 只给常见且可靠的词性，不确定时给最主要的 1 个。
4. 同一批每个词都要有一条 item，顺序与输入一致。"""


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _headers(config: LLMConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def build_messages(
    words: list[dict[str, str]], roots: list[dict[str, Any]], affixes: list[dict[str, Any]]
) -> list[dict[str, str]]:
    context = {
        "现有词根库（优先复用 key 与含义）": roots,
        "现有词缀库（优先复用 key 与含义）": affixes,
        "待拆解单词": words,
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请参考下面的既有词根/词缀库拆解单词，并返回 JSON：\n"
            + json.dumps(context, ensure_ascii=False, indent=1),
        },
    ]


def _post(config: LLMConfig, payload: dict[str, Any], *, transport: Any | None, timeout: float) -> dict[str, Any]:
    if not config.enabled:
        raise LLMNotConfigured("未配置大模型接口：请在设置页填写 Base URL 与模型名")
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.post(_endpoint(config.base_url), json=payload, headers=_headers(config))
    except httpx.HTTPError as exc:
        raise LLMError(f"请求模型失败：{exc}") from exc
    if response.status_code >= 400:
        raise LLMError(f"模型返回 HTTP {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError as exc:
        raise LLMError(f"模型响应不是 JSON：{response.text[:300]}") from exc


def annotate_batch(
    config: LLMConfig,
    words: list[dict[str, str]],
    roots: list[dict[str, Any]],
    affixes: list[dict[str, Any]],
    *,
    transport: Any | None = None,
    timeout: float = 90.0,
) -> list[dict[str, Any]]:
    """调用模型拆解一批单词；返回 items 列表（已校验 word 字段）。"""
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": build_messages(words, roots, affixes),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    data = _post(config, payload, transport=transport, timeout=timeout)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"模型响应结构异常：{str(data)[:300]}") from exc
    try:
        parsed = extract_json(content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"模型未返回合法 JSON：{str(content)[:300]}") from exc
    items = parsed.get("items")
    if not isinstance(items, list) or not items:
        raise LLMError("模型返回缺少 items 列表")
    expected = [w["term"].strip().lower() for w in words]
    cleaned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word") or "").strip()
        if word.lower() not in expected:
            continue
        breakdown = item.get("breakdown")
        cleaned.append(
            {
                "word": word,
                "breakdown": breakdown if isinstance(breakdown, list) else [],
                "mnemonic": str(item.get("mnemonic") or ""),
                "cognates": [str(x) for x in item.get("cognates") or [] if str(x).strip()],
                "derivatives": [str(x) for x in item.get("derivatives") or [] if str(x).strip()],
                "confusables": [str(x) for x in item.get("confusables") or [] if str(x).strip()],
            }
        )
    if not cleaned:
        raise LLMError("模型返回的 items 与待拆解单词不匹配")
    return cleaned


def annotate_pos_batch(
    config: LLMConfig,
    words: list[dict[str, str]],
    *,
    transport: Any | None = None,
    timeout: float = 90.0,
) -> list[dict[str, str]]:
    """给一批单词标注词性；返回 [{"word": ..., "pos": "n., v."}]。"""
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": POS_PROMPT},
            {
                "role": "user",
                "content": "请标注这些单词的词性，返回 JSON：\n"
                + json.dumps({"待标注单词": words}, ensure_ascii=False, indent=1),
            },
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    data = _post(config, payload, transport=transport, timeout=timeout)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"模型响应结构异常：{str(data)[:300]}") from exc
    try:
        parsed = extract_json(content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"模型未返回合法 JSON：{str(content)[:300]}") from exc
    items = parsed.get("items")
    if not isinstance(items, list) or not items:
        raise LLMError("模型返回缺少 items 列表")
    expected = {w["term"].strip().lower() for w in words}
    cleaned: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word") or "").strip()
        if word.lower() not in expected:
            continue
        raw = item.get("pos")
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = [str(x) for x in raw]
        else:
            values = []
        pos = ", ".join([x.strip() for x in values if x.strip()][:4])
        if pos:
            cleaned.append({"word": word, "pos": pos})
    if not cleaned:
        raise LLMError("模型返回的 items 与待标注单词不匹配")
    return cleaned


def test_connection(
    config: LLMConfig, *, transport: Any | None = None, timeout: float = 20.0
) -> dict[str, Any]:
    """用一个极小的请求验证 Base URL / Key / 模型名是否可用。"""
    if not config.enabled:
        raise LLMNotConfigured("未配置大模型接口：请填写 Base URL 与模型名")
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": "只回复 pong 四个字母"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    started = time.perf_counter()
    data = _post(config, payload, transport=transport, timeout=timeout)
    latency_ms = round((time.perf_counter() - started) * 1000)
    try:
        content = str(data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"模型响应结构异常：{str(data)[:200]}") from exc
    return {
        "ok": True,
        "latencyMs": latency_ms,
        "model": config.model,
        "sample": content[:80],
    }
