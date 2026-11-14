import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { IconRight, IconSearch } from "../components/Icons.jsx";

const TABS = [
  ["root", "词根"],
  ["prefix", "前缀"],
  ["suffix", "后缀"],
];

export default function Roots() {
  const [tab, setTab] = useState("root");
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "root") {
        const data = await api.roots({ q, pageSize: 100 });
        setItems(data.items);
      } else {
        const data = await api.affixes({ type: tab });
        setItems(data.items.filter((item) => !q || item.key.includes(q) || item.gloss.includes(q)));
      }
      setError("");
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [tab, q]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
        {TABS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`min-h-9 rounded-lg text-sm ${
              tab === value
                ? "bg-white font-medium text-indigo-700 shadow-sm dark:bg-slate-900 dark:text-indigo-300"
                : "text-slate-500 dark:text-slate-400"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="relative">
        <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
        <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索词根 / 词缀 / 含义" className="input pl-10" />
      </div>

      {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
      {loading ? <p className="text-sm text-slate-400">加载中…</p> : null}

      {!loading && items.length === 0 ? (
        <div className="card px-4 py-6 text-center text-sm text-slate-500 dark:text-slate-400">
          {tab === "root" ? "还没有词根数据：导入带标注的单词后会自动积累。" : "还没有词缀数据。"}
        </div>
      ) : null}

      <ul className="space-y-2">
        {items.map((item) => (
          <li key={`${tab}-${item.id}`}>
            <Link
              to={`/roots/${tab === "root" ? "root" : "affix"}/${item.id}`}
              className="card flex items-center justify-between px-4 py-3"
            >
              <div className="min-w-0">
                <p className="flex items-baseline gap-2">
                  <span className="text-lg font-semibold">{item.key}</span>
                  <span className="truncate text-sm text-slate-500 dark:text-slate-400">{item.gloss}</span>
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {item.words} 个词
                  {item.origin ? ` · ${item.origin}` : ""}
                </p>
              </div>
              <span className="flex items-center gap-1 text-xs text-slate-400">
                <IconRight className="h-4 w-4" />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
