export default function Progress({ done, target, label, tone = "indigo" }) {
  const percent = target > 0 ? Math.min(100, Math.round((done / target) * 100)) : 0;
  const tones = {
    indigo: "bg-indigo-500",
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
  };
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <span>{label}</span>
        <span className={done >= target && target > 0 ? "font-medium text-emerald-600 dark:text-emerald-400" : ""}>
          {done}/{target}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div className={`h-full rounded-full transition-all ${tones[tone] || tones.indigo}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
