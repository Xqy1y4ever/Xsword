import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { MARK_ANCHORS, MARK_LABELS } from "../lib/format.js";
import { IconRight } from "./Icons.jsx";
import Sheet from "./Sheet.jsx";

const TYPE_STYLES = {
  root: "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800",
  prefix: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800",
  suffix:
    "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800",
};

const TYPE_LABELS = { root: "词根", prefix: "前缀", suffix: "后缀" };

function Chip({ children, onClick, className = "" }) {
  const Tag = onClick ? "button" : "span";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={`inline-flex items-center rounded-lg border px-2 py-1 text-sm ${className} ${
        onClick ? "active:opacity-70" : ""
      }`}
    >
      {children}
    </Tag>
  );
}

/** 词源记忆卡片：拆解、词根词缀、同根词、衍生词、形象化联想 */
export default function MemoryCard({ memory, onMark, mark, compact = false }) {
  const [peek, setPeek] = useState(null);
  const [peekDetail, setPeekDetail] = useState(null);
  const [peekError, setPeekError] = useState("");

  if (!memory) return null;

  const rootMap = new Map((memory.roots || []).map((root) => [root.key, root.id]));
  const affixMap = new Map((memory.affixes || []).map((affix) => [affix.key, affix.id]));
  const breakdown = memory.breakdown || [];
  const sameRoot = memory.sameRootWords || [];
  const cognates = (memory.cognates || []).filter((item) => item.term);
  const derivatives = (memory.derivatives || []).filter((item) => item.term);
  const confusables = memory.confusables || [];

  async function openPeek(kind, id, label) {
    setPeek({ kind, id, label });
    setPeekDetail(null);
    setPeekError("");
    try {
      const detail = kind === "root" ? await api.root(id) : await api.affix(id);
      setPeekDetail(detail);
    } catch (error) {
      setPeekError(error.message);
    }
  }

  const sourceLabel = { seed: "离线标注", llm: "模型标注", manual: "手动编辑" }[memory.source] || "未标注";

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-medium">
          <span>记忆卡片</span>
          {memory.pos ? (
            <span className="rounded bg-slate-200/80 px-1.5 py-0.5 text-xs font-normal text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {memory.pos}
            </span>
          ) : null}
        </p>
        <span className="text-xs text-slate-400">
          {memory.status === "ok" ? sourceLabel : "暂无词源标注"}
        </span>
      </div>

      {breakdown.length > 0 ? (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          {breakdown.map((item, index) => {
            const kind = item.type === "prefix" || item.type === "suffix" ? item.type : "root";
            const rootId = rootMap.get(item.key);
            const affixId = affixMap.get(item.key);
            const clickable = kind === "root" ? Boolean(rootId) : Boolean(affixId);
            return (
              <Chip
                key={`${item.key}-${index}`}
                className={TYPE_STYLES[kind]}
                onClick={
                  clickable
                    ? () => openPeek(kind, kind === "root" ? rootId : affixId, item.key)
                    : undefined
                }
              >
                <span className="font-medium">{item.form || item.key}</span>
                <span className="ml-1 text-xs opacity-80">
                  {TYPE_LABELS[kind]}·{item.gloss}
                </span>
              </Chip>
            );
          })}
        </div>
      ) : null}

      {memory.mnemonic ? (
        <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">{memory.mnemonic}</p>
      ) : (
        <p className="text-sm text-slate-400">{memory.status === "ok" ? "标注里还没有形象化联想。" : "该词尚未做词源拆解。"}</p>
      )}

      {memory.roots?.length && breakdown.length === 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {memory.roots.map((root) => (
            <Chip key={root.id} className={TYPE_STYLES.root} onClick={() => openPeek("root", root.id, root.key)}>
              {root.key}
              <span className="ml-1 text-xs opacity-80">{root.gloss}</span>
            </Chip>
          ))}
        </div>
      ) : null}

      {sameRoot.length > 0 ? (
        <div className="mt-2">
          <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">同根词</p>
          <div className="flex flex-wrap gap-1.5">
            {sameRoot.map((word) => (
              <Link
                key={word.id}
                to={`/words?word=${word.id}`}
                className="inline-flex items-center rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm text-slate-700 active:opacity-70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                {word.term}
                <span className="ml-1 text-xs text-slate-400">{Math.round(word.mastery)}</span>
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      {cognates.length > 0 || derivatives.length > 0 || confusables.length > 0 ? (
        <div className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-300">
          {cognates.length > 0 ? (
            <p>
              <span className="text-xs text-slate-400">同根/关联：</span>
              {cognates.map((item) =>
                item.wordId ? (
                  <Link key={item.term} to={`/words?word=${item.wordId}`} className="mr-2 underline decoration-slate-300">
                    {item.term}
                  </Link>
                ) : (
                  <span key={item.term} className="mr-2">
                    {item.term}
                    <span className="text-xs text-slate-400">（未收录）</span>
                  </span>
                )
              )}
            </p>
          ) : null}
          {derivatives.length > 0 ? (
            <p>
              <span className="text-xs text-slate-400">衍生词：</span>
              {derivatives.map((item) =>
                item.wordId ? (
                  <Link key={item.term} to={`/words?word=${item.wordId}`} className="mr-2 underline decoration-slate-300">
                    {item.term}
                  </Link>
                ) : (
                  <span key={item.term} className="mr-2">
                    {item.term}
                    <span className="text-xs text-slate-400">（未收录）</span>
                  </span>
                )
              )}
            </p>
          ) : null}
          {confusables.length > 0 ? (
            <p>
              <span className="text-xs text-slate-400">易混：</span>
              {confusables.map((item, index) => (
                <span key={`${item.term || "c"}-${index}`} className="mr-2">
                  {item.term || item}
                </span>
              ))}
            </p>
          ) : null}
        </div>
      ) : null}

      {onMark ? (
        <div className="mt-3 border-t border-slate-200 pt-2 dark:border-slate-800">
          <p className="mb-1.5 text-xs text-slate-500 dark:text-slate-400">
            这个词你觉得有多熟？（对应熟练度 15 / 30 / 45 / 60）
          </p>
          <div className="grid grid-cols-4 gap-1.5">
            {[1, 2, 3, 4].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => onMark(value)}
                className={`min-h-10 rounded-lg border text-sm ${
                  mark === value
                    ? "border-indigo-400 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300"
                    : "border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                }`}
              >
                <span>{MARK_LABELS[value]}</span>
                <span className="ml-1 text-[10px] opacity-60">{MARK_ANCHORS[value]}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {!compact && memory.updatedAt ? (
        <p className="mt-2 text-right text-[11px] text-slate-400">更新于 {memory.updatedAt.replace("T", " ").slice(0, 16)}</p>
      ) : null}

      <Sheet
        open={Boolean(peek)}
        title={peek ? `${peek.kind === "root" ? "词根" : "词缀"} ${peek.label}` : ""}
        onClose={() => setPeek(null)}
      >
        {peekError ? <p className="text-sm text-rose-600">{peekError}</p> : null}
        {!peekDetail && !peekError ? <p className="text-sm text-slate-400">加载中…</p> : null}
        {peekDetail ? (
          <div className="space-y-3">
            <div>
              <p className="text-2xl font-semibold">{peekDetail.key}</p>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {peekDetail.gloss}
                {peekDetail.origin ? ` · ${peekDetail.origin}` : ""}
              </p>
            </div>
            <div>
              <p className="mb-1.5 text-xs text-slate-400">包含它的单词（{peekDetail.words.length}）</p>
              <ul className="space-y-1.5">
                {peekDetail.words.map((word) => (
                  <li key={word.wordId}>
                    <Link
                      to={`/words?word=${word.wordId}`}
                      onClick={() => setPeek(null)}
                      className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                    >
                      <span>
                        <span className="font-medium">{word.term}</span>
                        <span className="ml-2 text-sm text-slate-500 dark:text-slate-400">{word.meaning}</span>
                      </span>
                      <span className="flex items-center gap-1 text-xs text-slate-400">
                        {Math.round(word.mastery)}
                        <IconRight className="h-4 w-4" />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            {peekDetail.relatedRoots?.length ? (
              <div>
                <p className="mb-1.5 text-xs text-slate-400">常一起出现的词根</p>
                <div className="flex flex-wrap gap-1.5">
                  {peekDetail.relatedRoots.map((root) => (
                    <button
                      key={root.id}
                      type="button"
                      onClick={() => openPeek("root", root.id, root.key)}
                      className="rounded-lg border border-indigo-200 px-2 py-1 text-sm text-indigo-700 dark:border-indigo-800 dark:text-indigo-300"
                    >
                      {root.key}
                      <span className="ml-1 text-xs opacity-70">{root.gloss}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
