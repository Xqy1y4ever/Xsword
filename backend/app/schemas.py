"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class CycleSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycleSize: int = Field(ge=1, le=200)
    # 选义比例（0–1）；不传则保留当前值
    choiceRatio: float | None = Field(default=None, ge=0.0, le=1.0)


class CycleAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wordId: int = Field(ge=1)
    answer: str = Field(default="", max_length=300)
    responseMs: int = Field(default=0, ge=0)
    action: Literal["submit", "dont_know", "mastered"] = "submit"


class CycleAdjustIn(BaseModel):
    """拼写题写完后追加的选择：模糊（回滚熟练度）或已熟练（提到 95）。"""

    model_config = ConfigDict(extra="forbid")
    wordId: int = Field(ge=1)
    choice: Literal["fuzzy", "mastered"]


class WordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str = Field(min_length=1, max_length=120)
    meaning: str = Field(min_length=1, max_length=300)
    alt: str = Field(default="", max_length=300)
    phonetic: str = Field(default="", max_length=120)
    pos: str = Field(default="", max_length=60)
    example: str = Field(default="", max_length=600)
    tags: str = Field(default="", max_length=200)


class WordPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str | None = Field(default=None, min_length=1, max_length=120)
    meaning: str | None = Field(default=None, min_length=1, max_length=300)
    alt: str | None = Field(default=None, max_length=300)
    phonetic: str | None = Field(default=None, max_length=120)
    pos: str | None = Field(default=None, max_length=60)
    example: str | None = Field(default=None, max_length=600)
    tags: str | None = Field(default=None, max_length=200)


class ImportIn(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


class PurgeIn(BaseModel):
    confirm: str = Field(min_length=1, max_length=20)


class MarkIn(BaseModel):
    mark: int = Field(ge=0, le=4)


class BreakdownItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    form: str = ""
    type: str = "root"
    key: str = ""
    gloss: str = ""
    origin: str = ""
    note: str = ""


class AnnotationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    breakdown: list[BreakdownItem] = Field(default_factory=list)
    mnemonic: str = ""
    cognates: list[str] = Field(default_factory=list)
    derivatives: list[str] = Field(default_factory=list)
    confusables: list[str] = Field(default_factory=list)


class AnnotateIn(BaseModel):
    wordIds: list[int] = Field(min_length=1, max_length=20)


class LlmConfigIn(BaseModel):
    """apiKey 为 None 表示不修改；传空字符串表示清除。"""

    model_config = ConfigDict(extra="forbid")
    baseUrl: str | None = Field(default=None, max_length=500)
    apiKey: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=120)
    batchSize: int | None = Field(default=None, ge=1, le=50)


class AnnotateImportItem(AnnotationIn):
    model_config = ConfigDict(extra="ignore")
    word: str = ""
    term: str = ""
    source: str = "seed"


class AnnotateImportIn(BaseModel):
    items: list[AnnotateImportItem] = Field(min_length=1, max_length=500)


class SeedsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    words: list[dict[str, Any]] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
