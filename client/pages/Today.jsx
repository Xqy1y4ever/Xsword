import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../lib/api.js";
import { MASTERY_BAR, formatPercent } from "../lib/format.js";
import Empty from "../components/Empty.jsx";
import Progress from "../components/Progress.jsx";
import { IconRight } from "../components/Icons.jsx";

const LEVELS = [
  ["不认识", "vague"],
  ["模糊", "fuzzy"],
  ["认识", "known"],
  ["很熟", "mastered"],
];

export default function Today() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  function load() {
    api
      .today()
      .then(setData)
      .catch((loadError) => setError(loadError.message));
  }

  useEffect(load, []);

  const mastery = data?.mastery;
  const totalForBar = useMemo(() => (mastery ? Math.max(1, mastery.total) : 1), [mastery]);

  async function startCycle() {
    setStarting(true);
    setError("");
    try {
      await api.startCycle();
      navigate("/practice");
    } catch (startError) {
      setError(startError.message);
    } finally {
      setStarting(false);
    }
  }

  if (error && !data) {
    return <p className="card p-4 text-sm text-rose-600">{error}</p>;
  }
  if (!data) {
    return <p className="p-4 text-sm text-slate-400">加载中…</p>;
  }

  const active = data.activeCycle;
  const done = active ? active.answered : 0;
  const total = active ? active.size : data.settings.cycleSize;

  return (
    <div className="space-y-4">
      <section className="card p-4">
        <div className="mb-3 flex items-start justify-between">
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400">{data.date}</p>
            <h2 className="text-xl font-semibold">今日循环</h2>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-400">连续打卡</p>
            <p className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400">
              {data.streak}
              <span className="ml-0.5 text-sm font-normal text-slate-400">天</span>
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <Progress
            label={active ? "当前循环进度" : "下一轮循环词数"}
            done={active ? done : 0}
            target={total}
            tone={active ? "emerald" : "indigo"}
          />
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-xl bg-slate-50 py-2 dark:bg-slate-800/60">
              <p className="text-lg font-semibold">{data.today.cycles}</p>
              <p className="text-xs text-slate-400">今日完成循环</p>
            </div>
            <div className="rounded-xl bg-slate-50 py-2 dark:bg-slate-800/60">
              <p className="text-lg font-semibold">{data.today.answered}</p>
              <p className="text-xs text-slate-400">今日答题</p>
            </div>
            <div className="rounded-xl bg-slate-50 py-2 dark:bg-slate-800/60">
              <p className="text-lg font-semibold">{formatPercent(data.today.accuracy)}</p>
              <p className="text-xs text-slate-400">正确率</p>
            </div>
          </div>
          <p className="text-xs text-slate-400">
            每循环 {data.settings.cycleSize} 词 · 选义/拼写 {Math.round((data.settings.choiceRatio ?? 0.6) * 100)}/
            {100 - Math.round((data.settings.choiceRatio ?? 0.6) * 100)} · 可练词 {data.eligibleCount} 个（熟练度 &gt; 90 的词不再出现）
          </p>
        </div>

        {data.totalWords === 0 ? (
          <div className="mt-4">
            <Empty
              title="词库还是空的"
              description="先导入或添加单词，再开始循环。"
              action={
                <Link to="/words/import" className="btn-primary w-full">
                  去导入词库
                </Link>
              }
            />
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
            {active ? (
              <button type="button" onClick={() => navigate("/practice")} className="btn-primary w-full">
                继续当前循环（{done}/{active.size}）
                <IconRight className="h-5 w-5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={startCycle}
                disabled={starting || data.eligibleCount === 0}
                className="btn-primary w-full"
              >
                {starting ? "准备中…" : data.eligibleCount === 0 ? "没有可练的词了" : "开始新循环"}
                {data.eligibleCount > 0 ? <IconRight className="h-5 w-5" /> : null}
              </button>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Link to="/settings" className="btn-ghost text-sm">
                每循环 {data.settings.cycleSize} 词 · {Math.round((data.settings.choiceRatio ?? 0.6) * 100)}/
                {100 - Math.round((data.settings.choiceRatio ?? 0.6) * 100)}
              </Link>
              <Link to="/stats" className="btn-ghost text-sm">
                查看统计
              </Link>
            </div>
          </div>
        )}
      </section>

      <section className="card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium text-slate-600 dark:text-slate-300">掌握度分布</h3>
          <span className="text-xs text-slate-400">
            已学 {mastery.learned}/{mastery.total}
            {mastery.excluded > 0 ? ` · 已掌握 ${mastery.excluded}` : ""}
          </span>
        </div>
        <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          {LEVELS.map(([label, code]) => {
            const width = ((mastery[label] || 0) / totalForBar) * 100;
            if (width <= 0) return null;
            return <div key={code} className={MASTERY_BAR[code]} style={{ width: `${width}%` }} />;
          })}
        </div>
        <div className="mt-2 grid grid-cols-4 gap-1 text-center">
          {LEVELS.map(([label, code]) => (
            <div key={code}>
              <p className="text-base font-semibold">{mastery[label] || 0}</p>
              <p className="flex items-center justify-center gap-1 text-xs text-slate-400">
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${MASTERY_BAR[code]}`} />
                {label}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-400">
          规则：自评四档 = 不认识 15 / 模糊 30 / 认识 45 / 很熟 60。题型按熟练度门槛：&gt;50 才可能出拼写，
          &gt;60 不再出释义（50–60 两种都可能），目标 60% 选义 / 40% 拼写；熟练度越低越先被选。
          首次作答答错→15、3 秒内答对→45、3 秒外→30；之后答对 +15、答错 −15（每次只跨一个阶段）。
          同一个词最多连续出现两轮，第三轮自动跳过。
        </p>
      </section>

      <section className="card p-4">
        <h3 className="mb-2 text-sm font-medium text-slate-600 dark:text-slate-300">最近完成的循环</h3>
        {data.recentCycles.length === 0 ? (
          <p className="text-sm text-slate-400">还没有完成的循环。</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
            {data.recentCycles.map((cycle) => (
              <li key={cycle.id} className="flex items-center justify-between py-1.5">
                <span className="text-slate-500 dark:text-slate-400">{cycle.date}</span>
                <span>
                  {cycle.size} 题 · 答对 {cycle.correct}
                  <span className="ml-2 text-xs text-slate-400">
                    {cycle.size ? Math.round((cycle.correct / cycle.size) * 100) : 0}%
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
        {data.annotations.pending > 0 ? (
          <Link to="/words/import" className="mt-3 block text-xs text-amber-600 dark:text-amber-400">
            有 {data.annotations.pending} 个词还没有词源标注，去处理 →
          </Link>
        ) : null}
      </section>
    </div>
  );
}
