import { useState } from "react";

export default function Login({ onLogin }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!password) return;
    setBusy(true);
    setError("");
    try {
      await onLogin(password);
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-dvh w-full max-w-md flex-col justify-center px-6">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-2xl text-white">
          词
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">背单词</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">输入个人口令后开始今天的学习</p>
      </div>

      <form onSubmit={submit} className="space-y-3">
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="口令"
          autoComplete="current-password"
          className="input"
        />
        {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy ? "登录中…" : "登录"}
        </button>
      </form>

      <p className="mt-6 text-center text-xs leading-relaxed text-slate-400">
        单用户应用。服务端口令由
        <code className="mx-1 rounded bg-slate-100 px-1 py-0.5 text-[11px] dark:bg-slate-800">npm run set-password</code>
        生成后写入 .env。
      </p>
    </div>
  );
}
