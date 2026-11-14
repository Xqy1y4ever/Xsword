import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";

export default function ImportExport() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);
  const [health, setHealth] = useState(null);
  const [annotationText, setAnnotationText] = useState("");
  const [annotationResult, setAnnotationResult] = useState(null);
  const [purgeText, setPurgeText] = useState("");
  const [purgeDone, setPurgeDone] = useState("");

  useEffect(() => {
    api.annotateStatus().then(setStatus).catch(() => {});
    api.health().then(setHealth).catch(() => {});
  }, []);

  async function importWords() {
    if (!text.trim()) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await api.importWords(text);
      setResult(response);
      setText("");
      setStatus(await api.annotateStatus());
    } catch (importError) {
      setError(importError.message);
    } finally {
      setBusy(false);
    }
  }

  async function runAnnotation() {
    setBusy(true);
    setError("");
    try {
      let wordIds = [];
      const missing = await api.words({ annotation: "missing", pageSize: 20 });
      wordIds = missing.items.map((word) => word.id);
      if (wordIds.length === 0) {
        setError("没有需要标注的单词。");
        return;
      }
      await api.annotate(wordIds);
      setStatus(await api.annotateStatus());
    } catch (annotateError) {
      setError(annotateError.message);
    } finally {
      setBusy(false);
    }
  }

  async function importAnnotations() {
    if (!annotationText.trim()) return;
    setBusy(true);
    setError("");
    try {
      const items = JSON.parse(annotationText);
      const response = await api.importAnnotations(Array.isArray(items) ? items : items.items || []);
      setAnnotationResult(response);
      setStatus(await api.annotateStatus());
    } catch (annotateError) {
      setError(`标注导入失败：${annotateError.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function purge() {
    setBusy(true);
    setError("");
    try {
      await api.purgeWords(purgeText.trim());
      setPurgeDone("词库已清空");
      setPurgeText("");
      setStatus(await api.annotateStatus());
    } catch (purgeError) {
      setError(purgeError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <section className="card p-4">
        <h2 className="text-sm font-semibold">批量导入单词</h2>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          每行一条：<code className="rounded bg-slate-100 px-1 dark:bg-slate-800">单词 + 分隔符 + 释义</code>。
          分隔符支持 Tab、逗号、等号、冒号；# 开头为注释。重复单词会自动跳过。
        </p>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={8}
          placeholder={"glamorous,迷人的\nrubric\t评分标准\ncome of age,成年；成熟"}
          className="input mt-2 font-mono text-sm"
        />
        <div className="mt-2 flex gap-2">
          <button type="button" onClick={importWords} disabled={busy || !text.trim()} className="btn-primary flex-1">
            {busy ? "处理中…" : "导入"}
          </button>
          <Link to="/words" className="btn-ghost flex-1">
            返回词库
          </Link>
        </div>
        {result ? (
          <div className="mt-2 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
            成功导入 {result.added} 个词
            {result.skipped.length > 0 ? `，跳过 ${result.skipped.length} 行` : ""}
            {result.enqueued > 0 ? `，已排队标注 ${result.enqueued} 个词` : ""}
          </div>
        ) : null}
      </section>

      <section className="card p-4">
        <h2 className="text-sm font-semibold">导出与备份</h2>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <a href={api.exportUrl("json")} download className="btn-ghost">
            导出 JSON
          </a>
          <a href={api.exportUrl("csv")} download className="btn-ghost">
            导出 CSV
          </a>
        </div>
        <p className="mt-2 text-xs text-slate-400">JSON 保留全部字段，可作为备份长期保存。</p>
      </section>

      <section className="card p-4">
        <h2 className="text-sm font-semibold">词源标注</h2>
        {status ? (
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            共 {status.total} 词 · 已标注 {status.annotated} · 待处理 {status.pendingJobs} · 未标注 {status.missing}
          </p>
        ) : null}
        <p className="mt-1 text-xs text-slate-400">
          {health?.llmEnabled
            ? "已配置大模型接口：新词会自动逐个拆解词根词缀。"
            : "未配置模型：请在「设置 → 词源标注模型」里填写 Base URL 与模型名；也可用下面框导入离线标注 JSON。"}
        </p>
        <Link to="/settings" className="mt-1 block text-xs text-indigo-600 dark:text-indigo-400">
          去设置页配置模型 →
        </Link>
        <button
          type="button"
          onClick={runAnnotation}
          disabled={busy || !health?.llmEnabled}
          className="btn-ghost mt-2 w-full disabled:opacity-40"
        >
          标注未标注的单词（最多 20 个/次）
        </button>

        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-indigo-600 dark:text-indigo-400">离线标注 JSON 导入</summary>
          <textarea
            value={annotationText}
            onChange={(event) => setAnnotationText(event.target.value)}
            rows={6}
            placeholder={'[{"word":"pharmacy","breakdown":[{"form":"pharm","type":"root","key":"pharm","gloss":"药","origin":"Greek"}],"mnemonic":"...","cognates":["pharmaceutical"]}]'}
            className="input mt-2 font-mono text-xs"
          />
          <button type="button" onClick={importAnnotations} disabled={busy || !annotationText.trim()} className="btn-ghost mt-2 w-full">
            导入标注
          </button>
          {annotationResult ? (
            <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
              标注成功 {annotationResult.ok} 条，跳过 {annotationResult.skipped} 条，词根关联 {annotationResult.roots} 个
            </p>
          ) : null}
        </details>
      </section>

      <section className="card p-4">
        <h2 className="text-sm font-semibold text-rose-600 dark:text-rose-400">清空词库</h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          会删除所有单词、学习记录、词根词缀库与队列，不可恢复。请先导出备份。
        </p>
        <div className="mt-2 flex gap-2">
          <input
            value={purgeText}
            onChange={(event) => setPurgeText(event.target.value)}
            placeholder="输入 DELETE 确认"
            className="input"
          />
          <button
            type="button"
            onClick={purge}
            disabled={busy || purgeText.trim() !== "DELETE"}
            className="min-h-12 shrink-0 rounded-xl border border-rose-200 px-3 text-sm text-rose-600 disabled:opacity-40 dark:border-rose-900 dark:text-rose-400"
          >
            清空
          </button>
        </div>
        {purgeDone ? <p className="mt-2 text-xs text-emerald-600">{purgeDone}</p> : null}
      </section>

      {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
    </div>
  );
}
