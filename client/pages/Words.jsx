import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../lib/api.js";
import { MARK_LABELS, masteryStyle } from "../lib/format.js";
import Empty from "../components/Empty.jsx";
import MemoryCard from "../components/MemoryCard.jsx";
import Sheet from "../components/Sheet.jsx";
import WordForm from "../components/WordForm.jsx";
import { IconPlus, IconSearch, IconTrash } from "../components/Icons.jsx";

const SORTS = [
  ["newest", "最新"],
  ["weakest", "最不熟"],
  ["mastered", "最熟"],
  ["term", "字母序"],
];

export default function Words() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [memory, setMemory] = useState(null);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteStage, setDeleteStage] = useState(0);
  const [annotationEditor, setAnnotationEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const touched = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.words({ q, sort, page, pageSize: 20 });
      setData(response);
      setError("");
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [q, sort, page]);

  useEffect(() => {
    const timer = setTimeout(() => {
      load();
      touched.current = true;
    }, touched.current ? 250 : 0);
    return () => clearTimeout(timer);
  }, [load]);

  const openWord = useCallback(async (word) => {
    setSelected(word);
    setMemory(null);
    setDeleteStage(0);
    setMemoryLoading(true);
    try {
      const card = await api.annotation(word.id);
      setMemory(card);
    } catch (memoryError) {
      setError(memoryError.message);
    } finally {
      setMemoryLoading(false);
    }
  }, []);

  useEffect(() => {
    const wordId = Number(searchParams.get("word") || 0);
    if (!wordId) return;
    api
      .word(wordId)
      .then(openWord)
      .catch(() => {})
      .finally(() => {
        const next = new URLSearchParams(searchParams);
        next.delete("word");
        setSearchParams(next, { replace: true });
      });
  }, [searchParams, setSearchParams, openWord]);

  async function mark(value) {
    if (!selected) return;
    try {
      await api.setMark(selected.id, value);
      setSelected((previous) => ({ ...previous, userMark: value }));
      await load();
    } catch (markError) {
      setError(markError.message);
    }
  }

  async function removeWord() {
    if (!selected) return;
    if (deleteStage === 0) {
      setDeleteStage(1);
      return;
    }
    setBusy(true);
    try {
      await api.deleteWord(selected.id);
      setSelected(null);
      setMemory(null);
      await load();
    } catch (deleteError) {
      setError(deleteError.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveAnnotation() {
    if (!selected || !annotationEditor) return;
    setBusy(true);
    try {
      const payload = JSON.parse(annotationEditor);
      const card = await api.saveAnnotation(selected.id, payload);
      setMemory(card);
      setAnnotationEditor(null);
      await load();
    } catch (annotationError) {
      setError(`标注保存失败：${annotationError.message}`);
    } finally {
      setBusy(false);
    }
  }

  const items = data?.items || [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;

  return (
    <div className="space-y-3 pb-20">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
          <input
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            placeholder="搜索单词、释义、标签"
            className="input pl-10"
          />
        </div>
        <Link to="/words/import" className="btn-ghost shrink-0 px-3">
          导入
        </Link>
      </div>

      <div className="no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {SORTS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => {
              setSort(value);
              setPage(1);
            }}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm ${
              sort === value
                ? "bg-indigo-600 text-white"
                : "border border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}

      {loading && items.length === 0 ? <p className="p-2 text-sm text-slate-400">加载中…</p> : null}

      {!loading && items.length === 0 ? (
        <Empty
          title={q ? "没有匹配的单词" : "词库还是空的"}
          description={q ? "换个关键词试试。" : "先导入或添加一些单词。"}
          action={
            <Link to="/words/import" className="btn-primary w-full">
              去导入词库
            </Link>
          }
        />
      ) : null}

      <ul className="space-y-2">
        {items.map((word) => (
          <li key={word.id}>
            <button type="button" onClick={() => openWord(word)} className="card w-full px-4 py-3 text-left">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="flex items-baseline gap-2">
                    <span className="truncate text-lg font-semibold">{word.term}</span>
                    {word.pos ? (
                      <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        {word.pos}
                      </span>
                    ) : null}
                    {word.phonetic ? <span className="truncate text-xs text-slate-400">{word.phonetic}</span> : null}
                  </p>
                  <p className="mt-0.5 truncate text-sm text-slate-500 dark:text-slate-400">{word.meaning}</p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${masteryStyle(word.masteryCode)}`}>
                  {word.masteryLabel} {Math.round(word.mastery)}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                <span>已练 {word.seen} 次</span>
                {word.userMark > 0 ? <span>· 自评 {MARK_LABELS[word.userMark]}</span> : null}
                {word.annotationStatus !== "ok" ? (
                  <span className="text-amber-500">· {word.annotationStatus === "pending" ? "待标注" : "未标注"}</span>
                ) : null}
              </div>
            </button>
          </li>
        ))}
      </ul>

      {totalPages > 1 ? (
        <div className="flex items-center justify-between pt-2 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            className="btn-ghost min-h-10 px-3 disabled:opacity-40"
          >
            上一页
          </button>
          <span className="text-slate-500 dark:text-slate-400">
            {page}/{totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
            className="btn-ghost min-h-10 px-3 disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => {
          setEditing(null);
          setFormOpen(true);
        }}
        aria-label="新增单词"
        className="fixed bottom-24 right-4 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 active:scale-95"
      >
        <IconPlus className="h-6 w-6" />
      </button>

      <Sheet
        open={Boolean(selected)}
        title={selected ? selected.term : ""}
        onClose={() => {
          setSelected(null);
          setMemory(null);
        }}
        footer={
          selected ? (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setEditing(selected);
                  setFormOpen(true);
                }}
                className="btn-ghost flex-1"
              >
                编辑单词
              </button>
              <button
                type="button"
                onClick={removeWord}
                disabled={busy}
                className={`flex min-h-12 flex-1 items-center justify-center gap-1 rounded-xl border text-sm ${
                  deleteStage === 1
                    ? "border-rose-400 bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300"
                    : "border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300"
                }`}
              >
                <IconTrash className="h-4 w-4" />
                {deleteStage === 1 ? "确认删除" : "删除"}
              </button>
            </div>
          ) : null
        }
      >
        {selected ? (
          <div className="space-y-3">
            <div>
              <p className="flex items-baseline gap-2">
                <span className="text-2xl font-semibold">{selected.term}</span>
                {selected.pos ? (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    {selected.pos}
                  </span>
                ) : null}
                {selected.phonetic ? <span className="text-sm text-slate-400">{selected.phonetic}</span> : null}
              </p>
              <p className="mt-0.5 text-base text-slate-600 dark:text-slate-300">{selected.meaning}</p>
              {selected.alt ? <p className="mt-1 text-xs text-slate-400">其它写法：{selected.alt}</p> : null}
              {selected.example ? (
                <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm italic text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
                  {selected.example}
                </p>
              ) : null}
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <span className={`rounded-full px-2 py-0.5 ${masteryStyle(selected.masteryCode)}`}>
                  {selected.masteryLabel} {Math.round(selected.mastery)}
                </span>
                <span>已练 {selected.seen} 次</span>
                <span>对 {selected.correct} / 错 {selected.wrong}</span>
                {selected.tags ? <span>标签：{selected.tags}</span> : null}
              </div>
            </div>

            {memoryLoading ? <p className="text-sm text-slate-400">加载记忆卡片…</p> : null}
            {memory ? <MemoryCard memory={memory} mark={selected.userMark} onMark={mark} /> : null}

            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-400">
                标注状态：{selected.annotationStatus === "ok" ? "已标注" : selected.annotationStatus === "pending" ? "待标注" : "未标注"}
                {selected.annotationSource ? ` · ${selected.annotationSource}` : ""}
              </p>
              <button
                type="button"
                onClick={() =>
                  setAnnotationEditor(
                    JSON.stringify(
                      {
                        breakdown: memory?.breakdown || [],
                        mnemonic: memory?.mnemonic || "",
                        cognates: (memory?.cognates || []).map((item) => item.term),
                        derivatives: (memory?.derivatives || []).map((item) => item.term),
                        confusables: (memory?.confusables || []).map((item) => item.term || item),
                      },
                      null,
                      2
                    )
                  )
                }
                className="text-xs text-indigo-600 dark:text-indigo-400"
              >
                高级：编辑标注 JSON
              </button>
            </div>

            {annotationEditor !== null ? (
              <div className="space-y-2">
                <textarea
                  value={annotationEditor}
                  onChange={(event) => setAnnotationEditor(event.target.value)}
                  rows={10}
                  className="input font-mono text-xs"
                />
                <div className="flex gap-2">
                  <button type="button" onClick={() => setAnnotationEditor(null)} className="btn-ghost flex-1">
                    取消
                  </button>
                  <button type="button" onClick={saveAnnotation} disabled={busy} className="btn-primary flex-1">
                    保存标注
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </Sheet>

      <WordForm
        open={formOpen}
        word={editing}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        onSaved={async () => {
          setFormOpen(false);
          setEditing(null);
          setSelected(null);
          await load();
        }}
      />
    </div>
  );
}
