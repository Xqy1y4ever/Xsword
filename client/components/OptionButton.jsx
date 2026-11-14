export default function OptionButton({ children, state = "idle", disabled, onClick }) {
  const styles = {
    idle: "border-slate-200 bg-white text-slate-800 active:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
    correct: "border-emerald-400 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200",
    wrong: "border-rose-400 bg-rose-50 text-rose-800 dark:border-rose-700 dark:bg-rose-950/50 dark:text-rose-200",
    muted: "border-slate-200 bg-white text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-500",
  };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex min-h-14 w-full items-center rounded-xl border px-4 py-3 text-left text-base leading-relaxed transition ${styles[state]}`}
    >
      {children}
    </button>
  );
}
