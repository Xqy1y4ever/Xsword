import { Link, Outlet, useLocation } from "react-router-dom";

import { IconBook, IconChart, IconSettings, IconSun } from "./Icons.jsx";

function TabBar({ pathname }) {
  const tabs = [
    { to: "/", label: "今日", icon: IconSun, match: (path) => path === "/" },
    {
      to: "/words",
      label: "词库",
      icon: IconBook,
      match: (path) => path.startsWith("/words") || path.startsWith("/roots"),
    },
    { to: "/stats", label: "统计", icon: IconChart, match: (path) => path.startsWith("/stats") },
  ];
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 mx-auto w-full max-w-md border-t border-slate-200/80 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
      <div className="grid grid-cols-3">
        {tabs.map(({ to, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <Link
              key={to}
              to={to}
              className={`flex min-h-14 flex-col items-center justify-center gap-0.5 py-2 text-xs ${
                active ? "text-indigo-600 dark:text-indigo-400" : "text-slate-500 dark:text-slate-400"
              }`}
            >
              <Icon className="h-6 w-6" />
              <span>{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

const TITLES = [
  [/^\/$/, "今日"],
  [/^\/words\/import/, "导入导出"],
  [/^\/words/, "词库"],
  [/^\/roots/, "词根词缀"],
  [/^\/stats/, "统计"],
  [/^\/settings/, "设置"],
  [/^\/practice/, "练习"],
];

export default function Layout() {
  const { pathname } = useLocation();
  const isPractice = pathname.startsWith("/practice");
  const title = TITLES.find(([pattern]) => pattern.test(pathname))?.[1] || "背单词";

  if (isPractice) {
    return (
      <div className="mx-auto h-dvh w-full max-w-md overflow-y-auto">
        <Outlet />
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-dvh w-full max-w-md flex-col">
      <header className="safe-top sticky top-0 z-20 border-b border-slate-200/70 bg-slate-50/90 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
        <div className="flex h-14 items-center justify-between px-4">
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
          <Link
            to="/settings"
            aria-label="设置"
            className="flex h-10 w-10 items-center justify-center rounded-full text-slate-500 active:bg-slate-200 dark:text-slate-400 dark:active:bg-slate-800"
          >
            <IconSettings className="h-5 w-5" />
          </Link>
        </div>
      </header>
      <main className="flex-1 overflow-y-auto px-4 pb-24 pt-3">
        <Outlet />
      </main>
      <TabBar pathname={pathname} />
    </div>
  );
}
