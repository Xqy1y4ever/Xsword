import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../lib/api.js";

const EMPTY_LLM = { baseUrl: "", model: "", batchSize: 20, apiKey: "" };

export default function Settings({ onLogout }) {
  const navigate = useNavigate();
  const [cycleSize, setCycleSize] = useState(20);
  const [choiceRatio, setChoiceRatio] = useState(60);
  const [cycleMessage, setCycleMessage] = useState("");
  const [cycleError, setCycleError] = useState("");
  const [cycleBusy, setCycleBusy] = useState(false);

  const [health, setHealth] = useState(null);
  const [annotations, setAnnotations] = useState(null);
  const [error, setError] = useState("");

  const [llm, setLlm] = useState(null);
  const [llmForm, setLlmForm] = useState(EMPTY_LLM);
  const [llmMessage, setLlmMessage] = useState("");
  const [llmError, setLlmError] = useState("");
  const [llmBusy, setLlmBusy] = useState(false);

  useEffect(() => {
    // 单个接口失败不应该把整页数据一起拖垮（之前 Promise.all 会这样）
    Promise.allSettled([
      api.settings().then((data) => {
        setCycleSize(data.cycleSize);
        if (typeof data.choiceRatio === "number") setChoiceRatio(Math.round(data.choiceRatio * 100));
      }),
      api.health().then(setHealth),
      api.annotateStatus().then(setAnnotations),
      api.llmConfig().then((config) => {
        setLlm(config);
        setLlmForm({
          baseUrl: config.baseUrl,
          model: config.model,
          batchSize: config.batchSize,
          apiKey: "",
        });
      }),
    ]).then((results) => {
      const failed = results.find((result) => result.status === "rejected");
      if (failed) {
        setError(`部分数据加载失败：${failed.reason?.message || "未知错误"}，刷新页面重试`);
      }
    });
  }, []);

  async function saveCycle(event) {
    event.preventDefault();
    const size = Number(cycleSize);
    if (!Number.isFinite(size) || size < 1 || size > 200) {
      setCycleError("每循环词数需要在 1–200 之间");
      return;
    }
    const ratio = Number(choiceRatio);
    if (!Number.isFinite(ratio) || ratio < 0 || ratio > 100) {
      setCycleError("选义比例需要在 0–100% 之间");
      return;
    }
    setCycleBusy(true);
    setCycleError("");
    setCycleMessage("");
    try {
      const saved = await api.saveSettings({
        cycleSize: Math.round(size),
        choiceRatio: ratio / 100,
      });
      setCycleSize(saved.cycleSize);
      if (typeof saved.choiceRatio === "number") setChoiceRatio(Math.round(saved.choiceRatio * 100));
      setCycleMessage("已保存。当前循环不受影响，下一轮循环按新词数与新比例开始。");
    } catch (saveError) {
      setCycleError(saveError.message);
    } finally {
      setCycleBusy(false);
    }
  }

  async function saveLlm(event) {
    event.preventDefault();
    setLlmBusy(true);
    setLlmError("");
    setLlmMessage("");
    try {
      const payload = {
        baseUrl: llmForm.baseUrl.trim(),
        model: llmForm.model.trim(),
        batchSize: Number(llmForm.batchSize) || 20,
      };
      if (llmForm.apiKey.trim()) payload.apiKey = llmForm.apiKey.trim();
      const saved = await api.saveLlmConfig(payload);
      setLlm(saved);
      setLlmForm((previous) => ({ ...previous, apiKey: "" }));
      setHealth(await api.health());
      setLlmMessage(saved.enabled ? "已保存，新词会上传到模型逐个拆解标注。" : "已保存，但 Base URL 与模型名都填好后才算启用。");
    } catch (saveError) {
      setLlmError(saveError.message);
    } finally {
      setLlmBusy(false);
    }
  }

  async function clearKey() {
    setLlmBusy(true);
    setLlmError("");
    setLlmMessage("");
    try {
      const saved = await api.saveLlmConfig({ apiKey: "" });
      setLlm(saved);
      setLlmMessage("已清除保存的 API Key。");
    } catch (saveError) {
      setLlmError(saveError.message);
    } finally {
      setLlmBusy(false);
    }
  }

  async function testLlm() {
    setLlmBusy(true);
    setLlmError("");
    setLlmMessage("");
    try {
      const result = await api.testLlm();
      setLlmMessage(`连接成功（${result.latencyMs}ms）：模型回复「${result.sample || "空"}」`);
    } catch (testError) {
      setLlmError(`连接失败：${testError.message}`);
    } finally {
      setLlmBusy(false);
    }
  }

  async function handleLogout() {
    await onLogout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="space-y-3">
      {error ? (
        <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          {error}
        </p>
      ) : null}
      <section className="card p-4">
        <h2 className="text-sm font-semibold">循环设置</h2>
        <form onSubmit={saveCycle} className="mt-3 space-y-3">
          <label className="block">
            <span className="mb-1 flex items-center justify-between text-sm text-slate-600 dark:text-slate-300">
              每个循环的单词数
              <span className="text-lg font-semibold text-indigo-600 dark:text-indigo-400">{cycleSize}</span>
            </span>
            <input
              type="range"
              min="1"
              max="100"
              step="1"
              value={Math.min(100, cycleSize)}
              onChange={(event) => setCycleSize(Number(event.target.value))}
              className="w-full accent-indigo-600"
            />
            <input
              type="number"
              min="1"
              max="200"
              value={cycleSize}
              onChange={(event) => setCycleSize(Number(event.target.value))}
              className="input mt-2"
            />
          </label>
          <label className="block">
            <span className="mb-1 flex items-center justify-between text-sm text-slate-600 dark:text-slate-300">
              选义 / 拼写比例
              <span className="text-lg font-semibold text-indigo-600 dark:text-indigo-400">
                {choiceRatio}% / {100 - choiceRatio}%
              </span>
            </span>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={choiceRatio}
              onChange={(event) => setChoiceRatio(Number(event.target.value))}
              className="w-full accent-indigo-600"
            />
            <div className="mt-1 flex items-center gap-2 text-xs text-slate-400">
              <span>0% 全拼写</span>
              <span className="flex-1 text-center">默认 60% 选义 / 40% 拼写</span>
              <span>100% 全选义</span>
            </div>
          </label>
          <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            循环规则：自评四档 = 不认识 15 / 模糊 30 / 认识 45 / 很熟 60。题型按熟练度门槛：&gt;50 才可能出拼写，
            &gt;60 不再出释义（50–60 两种都可能），题目数量按上面的比例四舍五入；熟练度越低越先被选。
            首次作答答错→15，3 秒内答对→45，3 秒外→30；之后答对 +15、答错 −15（每次只跨一个阶段）。
            拼写题只有「已熟练」自评（→95）；循环结束后会把 ≤30 分的卡片再列一遍，点「已读」每张 +10 分。
            同一个词最多连续出现两轮，第三轮自动跳过。
          </p>
          {cycleMessage ? <p className="text-sm text-emerald-600 dark:text-emerald-400">{cycleMessage}</p> : null}
          {cycleError ? <p className="text-sm text-rose-600 dark:text-rose-400">{cycleError}</p> : null}
          <button type="submit" disabled={cycleBusy} className="btn-primary w-full">
            {cycleBusy ? "保存中…" : "保存循环设置"}
          </button>
        </form>
      </section>

      <section className="card p-4">
        <div className="flex items-start justify-between">
          <h2 className="text-sm font-semibold">词源标注模型</h2>
          <span
            className={`rounded-full px-2 py-0.5 text-xs ${
              llm?.enabled
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
                : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            }`}
          >
            {llm?.enabled ? `已启用 · ${llm.model}` : "未启用"}
          </span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          配置保存在服务器数据库里（不写 .env）。新增或导入的词会自动调用模型拆解词根词缀；
          Key 只在服务端使用，接口只返回末四位。
        </p>

        {llm ? (
          <form onSubmit={saveLlm} className="mt-3 space-y-3">
            <label className="block">
              <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">Base URL（OpenAI 兼容）</span>
              <input
                value={llmForm.baseUrl}
                onChange={(event) => setLlmForm({ ...llmForm, baseUrl: event.target.value })}
                placeholder="https://api.deepseek.com/v1"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                className="input"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">模型名</span>
              <input
                value={llmForm.model}
                onChange={(event) => setLlmForm({ ...llmForm, model: event.target.value })}
                placeholder="deepseek-chat / gpt-4o-mini / qwen-plus"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                className="input"
              />
            </label>
            <label className="block">
              <span className="mb-1 flex items-center justify-between text-sm text-slate-600 dark:text-slate-300">
                API Key
                <span className="text-xs text-slate-400">
                  {llm.apiKeySet ? `已保存 ${llm.apiKeyHint}` : "未配置"}
                </span>
              </span>
              <input
                type="password"
                value={llmForm.apiKey}
                onChange={(event) => setLlmForm({ ...llmForm, apiKey: event.target.value })}
                placeholder={llm.apiKeySet ? "留空表示不修改" : "sk-..."}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                className="input"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">单批词数（1–50）</span>
              <input
                type="number"
                min="1"
                max="50"
                value={llmForm.batchSize}
                onChange={(event) => setLlmForm({ ...llmForm, batchSize: Number(event.target.value) })}
                className="input"
              />
            </label>

            {llmMessage ? <p className="text-sm text-emerald-600 dark:text-emerald-400">{llmMessage}</p> : null}
            {llmError ? <p className="text-sm text-rose-600 dark:text-rose-400">{llmError}</p> : null}

            <div className="flex gap-2">
              <button type="submit" disabled={llmBusy} className="btn-primary flex-1">
                {llmBusy ? "处理中…" : "保存配置"}
              </button>
              <button
                type="button"
                onClick={testLlm}
                disabled={llmBusy || !llm.enabled}
                className="btn-ghost flex-1 disabled:opacity-40"
              >
                测试连接
              </button>
            </div>
            {llm.apiKeySet ? (
              <button type="button" onClick={clearKey} disabled={llmBusy} className="text-xs text-rose-500 dark:text-rose-400">
                清除已保存的 Key
              </button>
            ) : null}
            {llm.updatedAt ? (
              <p className="text-right text-[11px] text-slate-400">更新于 {llm.updatedAt.replace("T", " ").slice(0, 16)}</p>
            ) : null}
          </form>
        ) : (
          <p className="mt-2 text-sm text-slate-400">加载中…</p>
        )}
      </section>

      <section className="card p-4">
        <h2 className="text-sm font-semibold">词库与标注</h2>
        <div className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-300">
          <p className="flex justify-between">
            <span>单词总数</span>
            <span className="font-medium">{annotations?.total ?? "—"}</span>
          </p>
          <p className="flex justify-between">
            <span>已标注</span>
            <span className="font-medium">{annotations?.annotated ?? "—"}</span>
          </p>
          <p className="flex justify-between">
            <span>未标注</span>
            <span className="font-medium text-amber-600 dark:text-amber-400">{annotations?.missing ?? "—"}</span>
          </p>
          <p className="flex justify-between">
            <span>标注流水线</span>
            <span className={`font-medium ${health?.llmEnabled ? "text-emerald-600 dark:text-emerald-400" : "text-slate-400"}`}>
              {health?.llmEnabled ? `已启用 · ${health.llmModel || "OpenAI 兼容"}` : "未配置"}
            </span>
          </p>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Link to="/words/import" className="btn-ghost">
            导入 / 导出
          </Link>
          <Link to="/roots" className="btn-ghost">
            词根词缀库
          </Link>
        </div>
      </section>

      <section className="card p-4">
        <h2 className="text-sm font-semibold">账号</h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          单用户应用，口令以 scrypt 哈希保存在服务器 .env 中，不入库、不进 git。
        </p>
        <button type="button" onClick={handleLogout} className="btn-ghost mt-3 w-full">
          退出登录
        </button>
      </section>

      <section className="card p-4">
        <h2 className="text-sm font-semibold">关于</h2>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          背单词 v1.0 · 循环制 · 按熟练度自动切换「英→中选义 / 中→英拼写」· 词源记忆卡片。
        </p>
      </section>
    </div>
  );
}
