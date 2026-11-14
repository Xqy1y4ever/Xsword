export const MARK_LABELS = { 0: "未标记", 1: "不认识", 2: "模糊", 3: "认识", 4: "很熟" };

// 选义题自评四档对应的熟练度分数
export const MARK_ANCHORS = { 1: 15, 2: 30, 3: 45, 4: 60 };

export const MODE_LABELS = { en2cn: "英→中选义", cn2en: "中→英拼写" };

export const MASTERY_STYLES = {
  vague: "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300",
  fuzzy: "bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300",
  known: "bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300",
  mastered: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300",
};

export const MASTERY_BAR = {
  vague: "bg-rose-400",
  fuzzy: "bg-amber-400",
  known: "bg-sky-400",
  mastered: "bg-emerald-400",
};

export function masteryStyle(code) {
  return MASTERY_STYLES[code] || "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
}

export function formatPercent(value, digits = 0) {
  const number = Number(value || 0);
  return `${number.toFixed(digits)}%`;
}

export function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function formatDuration(ms) {
  if (!ms) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function groupBy(list, keyFn) {
  return list.reduce((acc, item) => {
    const key = keyFn(item);
    (acc[key] = acc[key] || []).push(item);
    return acc;
  }, {});
}
