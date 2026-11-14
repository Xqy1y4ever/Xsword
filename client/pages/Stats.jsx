import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { MASTERY_BAR, formatPercent } from "../lib/format.js";

const LEVELS = [
  ["不认识", "vague"],
  ["模糊", "fuzzy"],
  ["认识", "known"],
  ["很熟", "mastered"],
];

export default function Stats() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .stats()
      .then(setData)
      .catch((loadError) => setError(loadError.message));
  }, []);

  if (error) return <p className="card p-4 text-sm text-rose-600">{error}</p>;
  if (!data) return <p className="p-4 text-sm text-slate-400">加载中…</p>;

  const mastery = data.mastery;
  const maxAnswered = Math.max(1, ...data.history.map((day) => day.answered));

  return (
    <div className="space-y-3">
      <section className="card p-4">
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-2xl font-semibold">{data.totals.seen}</p>
            <p className="text-xs text-slate-400">累计答题</p>
          </div>
          <div>
            <p className="text-2xl font-semibold">{formatPercent(data.totals.accuracy)}</p>
            <p className="text-xs text-slate-400">累计正确率</p>
          </div>
          <div>
            <p className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400">{data.streak}</p>
            <p className="text-xs text-slate-400">连续天数</p>
          </div>
        </div>
      </section>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-medium text-slate-600 dark:text-slate-300">循环</h2>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-slate-50 py-2 dark:bg-slate-800/60">
            <p className="text-lg font-semibold">{data.totals.cyclesToday}</p>
            <p className="text-xs text-slate-400">今日完成</p>
          </div>
          <div className="rounded-xl bg-slate-50 py-2 dark:bg-slate-800/60">
            <p className="text-lg font-semibold">{data.totals.cycles}</p>
            <p className="text-xs text-slate-400">累计循环</p>
          </div>
          <div className="rounded-xl bg-slate-50 py-2 dark:bg-slate-800/60">
            <p className="text-lg font-semibold">{data.today.answered}</p>
            <p className="text-xs text-slate-400">今日答题</p>
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          每循环 {data.settings.cycleSize} 词 · 可练 {data.eligibleCount} 词 · 已掌握（&gt;90）{mastery.excluded} 词
        </p>
      </section>

      <section className="card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-600 dark:text-slate-300">掌握度分布</h2>
          <span className="text-xs text-slate-400">
            {mastery.learned}/{mastery.total} 已学
          </span>
        </div>
        <div className="space-y-2">
          {LEVELS.map(([label, code]) => {
            const count = mastery[label] || 0;
            const percent = mastery.total ? Math.round((count / mastery.total) * 100) : 0;
            return (
              <div key={code}>
                <div className="mb-0.5 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                  <span>{label}</span>
                  <span>
                    {count} 个 · {percent}%
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div className={`h-full rounded-full ${MASTERY_BAR[code]}`} style={{ width: `${percent}%` }} />
                </div>
              </div>
            );
          })}
        </div>
        {mastery.unseen > 0 ? <p className="mt-2 text-xs text-slate-400">未学 {mastery.unseen} 个</p> : null}
      </section>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-medium text-slate-600 dark:text-slate-300">近 7 天</h2>
        {data.history.length === 0 ? (
          <p className="text-sm text-slate-400">还没有学习记录。</p>
        ) : (
          <div className="flex h-32 items-end justify-between gap-2">
            {data.history.map((day) => (
              <div key={day.date} className="flex flex-1 flex-col items-center gap-1">
                <span className="text-[10px] text-slate-400">{day.correct}</span>
                <div className="flex w-full flex-1 items-end">
                  <div
                    className="w-full rounded-t-md bg-indigo-400 dark:bg-indigo-500"
                    style={{ height: `${Math.max(4, Math.round((day.answered / maxAnswered) * 100))}%` }}
                    title={`${day.date} 答题 ${day.answered}，正确 ${day.correct}`}
                  />
                </div>
                <span className="text-[10px] text-slate-400">{day.date.slice(5)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-medium text-slate-600 dark:text-slate-300">错得最多的词</h2>
        {data.weakWords.length === 0 ? (
          <p className="text-sm text-slate-400">还没有错题记录。</p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.weakWords.map((word) => (
              <li key={word.wordId}>
                <Link to={`/words?word=${word.wordId}`} className="flex items-center justify-between py-2">
                  <span className="min-w-0">
                    <span className="font-medium">{word.term}</span>
                    <span className="ml-2 truncate text-sm text-slate-500 dark:text-slate-400">{word.meaning}</span>
                  </span>
                  <span className="ml-2 shrink-0 text-right text-xs text-slate-400">
                    错 {word.wrong} · 熟练度 {Math.round(word.mastery)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
