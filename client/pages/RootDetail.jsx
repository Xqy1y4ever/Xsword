import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../lib/api.js";
import { masteryStyle } from "../lib/format.js";
import { IconBack, IconRight } from "../components/Icons.jsx";

const KIND_LABELS = { root: "词根", affix: "词缀" };

export default function RootDetail() {
  const { kind, id } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const request = kind === "affix" ? api.affix(Number(id)) : api.root(Number(id));
    request.then(setDetail).catch((loadError) => setError(loadError.message));
  }, [kind, id]);

  if (error) {
    return (
      <div className="space-y-3">
        <button type="button" onClick={() => navigate(-1)} className="btn-ghost w-full">
          返回
        </button>
        <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
      </div>
    );
  }

  if (!detail) return <p className="text-sm text-slate-400">加载中…</p>;

  return (
    <div className="space-y-3">
      <button type="button" onClick={() => navigate(-1)} className="btn-ghost w-full justify-start px-3">
        <IconBack className="h-4 w-4" />
        返回词根词缀
      </button>

      <section className="card p-4">
        <p className="text-xs text-slate-400">
          {KIND_LABELS[kind] || "词根"}
          {detail.type ? ` · ${detail.type === "prefix" ? "前缀" : "后缀"}` : ""}
        </p>
        <p className="mt-0.5 text-3xl font-semibold tracking-tight">{detail.key}</p>
        <p className="mt-1 text-base text-slate-600 dark:text-slate-300">{detail.gloss}</p>
        {detail.origin ? <p className="mt-1 text-xs text-slate-400">语源：{detail.origin}</p> : null}
        {detail.note ? <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{detail.note}</p> : null}
        <p className="mt-2 text-xs text-slate-400">
          {detail.words.length} 个词共享这一{kind === "affix" ? "词缀" : "词根"}
        </p>
      </section>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-medium text-slate-600 dark:text-slate-300">词族</h2>
        <ul className="space-y-1.5">
          {detail.words.map((word) => (
            <li key={word.wordId}>
              <Link
                to={`/words?word=${word.wordId}`}
                className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              >
                <span className="min-w-0">
                  <span className="font-medium">{word.term}</span>
                  <span className="ml-2 truncate text-sm text-slate-500 dark:text-slate-400">{word.meaning}</span>
                </span>
                <span className="ml-2 flex shrink-0 items-center gap-1">
                  <span className={`rounded-full px-2 py-0.5 text-xs ${masteryStyle(word.mastery >= 80 ? "mastered" : word.mastery >= 60 ? "known" : word.mastery >= 30 ? "fuzzy" : "vague")}`}>
                    {Math.round(word.mastery)}
                  </span>
                  <IconRight className="h-4 w-4 text-slate-300" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {detail.relatedRoots?.length ? (
        <section className="card p-4">
          <h2 className="mb-2 text-sm font-medium text-slate-600 dark:text-slate-300">常一起出现的词根</h2>
          <div className="flex flex-wrap gap-1.5">
            {detail.relatedRoots.map((root) => (
              <Link
                key={root.id}
                to={`/roots/root/${root.id}`}
                className="rounded-lg border border-indigo-200 px-2 py-1 text-sm text-indigo-700 dark:border-indigo-800 dark:text-indigo-300"
              >
                {root.key}
                <span className="ml-1 text-xs opacity-70">{root.gloss}</span>
                <span className="ml-1 text-xs opacity-50">×{root.shared}</span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
