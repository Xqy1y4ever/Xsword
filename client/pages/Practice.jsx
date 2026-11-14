import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../lib/api.js";
import { MODE_LABELS, formatPercent } from "../lib/format.js";
import MemoryCard from "../components/MemoryCard.jsx";
import OptionButton from "../components/OptionButton.jsx";
import { IconBack, IconCheck, IconRight } from "../components/Icons.jsx";

export default function Practice() {
  const navigate = useNavigate();
  const [cycle, setCycle] = useState(null);
  const [question, setQuestion] = useState(null);
  const [finished, setFinished] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [peekMemory, setPeekMemory] = useState(null);
  const [peekLoading, setPeekLoading] = useState(false);
  const [reviewCards, setReviewCards] = useState([]);
  const [adjustChoice, setAdjustChoice] = useState("");
  const [adjustMessage, setAdjustMessage] = useState("");
  const [adjustBusy, setAdjustBusy] = useState(false);
  const startRef = useRef(Date.now());
  const inputRef = useRef(null);

  useEffect(() => {
    setAdjustChoice("");
    setAdjustMessage("");
    setAdjustBusy(false);
  }, [result?.wordId]);

  useEffect(() => {
    if (!finished || !cycle?.id) return undefined;
    let alive = true;
    api
      .cycleReviewCards(cycle.id)
      .then((data) => {
        if (alive) setReviewCards(data.cards || []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [finished, cycle?.id]);

  async function readCard(wordId) {
    if (!cycle) return;
    try {
      const data = await api.markCardRead(cycle.id, wordId);
      setReviewCards((previous) =>
        previous.map((card) =>
          card.wordId === wordId
            ? { ...card, mastery: data.mastery, masteryLabel: data.masteryLabel, cardRead: true }
            : card
        )
      );
    } catch (readError) {
      setError(readError.message);
    }
  }

  const loadQuestion = useCallback(async (cycleId) => {
    const payload = await api.cycleNext(cycleId);
    setCycle(payload.cycle);
    if (payload.finished) {
      setFinished(true);
      setQuestion(null);
    } else {
      setFinished(false);
      setQuestion(payload.question);
      startRef.current = Date.now();
    }
  }, []);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const current = await api.currentCycle();
      let active = current.cycle;
      if (!active) {
        const started = await api.startCycle();
        active = started.cycle;
      }
      setCycle(active);
      await loadQuestion(active.id);
    } catch (bootstrapError) {
      setError(bootstrapError.message);
    } finally {
      setLoading(false);
    }
  }, [loadQuestion]);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (question && question.mode === "cn2en" && !result) {
      const timer = setTimeout(() => inputRef.current?.focus(), 120);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [question, result]);

  async function submit(action, answerValue = "") {
    if (!question || !cycle || busy || result) return;
    setBusy(true);
    setError("");
    try {
      const responseMs = Math.max(300, Date.now() - startRef.current);
      const data = await api.cycleAnswer(cycle.id, {
        wordId: question.wordId,
        answer: answerValue,
        responseMs,
        action,
      });
      setResult(data);
      setCycle(data.cycle);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setBusy(false);
    }
  }

  async function chooseAdjust(choice) {
    if (!cycle || !result) return;
    setAdjustBusy(true);
    setError("");
    try {
      const data = await api.adjustAnswer(cycle.id, result.wordId, choice);
      setAdjustChoice(choice);
      setAdjustMessage(
        choice === "fuzzy"
          ? `已回滚到答题前：熟练度 ${Math.round(data.masteryAfter)}`
          : `已标记为已熟练：熟练度 ${Math.round(data.masteryAfter)}，不再进入循环`
      );
      setResult((previous) =>
        previous
          ? {
              ...previous,
              masteryAfter: data.masteryAfter,
              masteryLabel: data.masteryLabel,
              masteryCode: data.masteryCode,
            }
          : previous
      );
    } catch (adjustError) {
      setError(adjustError.message);
    } finally {
      setAdjustBusy(false);
    }
  }

  // 答完一题后，按回车进入下一题（正在用输入法组词、或在「模糊/已熟练」按钮上时除外）
  useEffect(() => {
    if (!result || finished || busy) return undefined;
    function onKeyDown(event) {
      if (event.key !== "Enter" || event.repeat || event.isComposing || event.keyCode === 229) return;
      const target = event.target instanceof Element ? event.target : null;
      const tag = target ? target.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if (target && target.closest("[data-enter-stays]")) return;
      event.preventDefault();
      next();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [result, finished, busy]);

  async function next() {
    if (!cycle) return;
    if (result?.cycleFinished) {
      setFinished(true);
      return;
    }
    setResult(null);
    setDraft("");
    setShowHint(false);
    setPeekMemory(null);
    try {
      await loadQuestion(cycle.id);
    } catch (nextError) {
      setError(nextError.message);
    }
  }

  async function mark(value) {
    if (!result) return;
    try {
      await api.setMark(result.wordId, value);
      setResult((previous) => (previous ? { ...previous, userMark: value } : previous));
    } catch (markError) {
      setError(markError.message);
    }
  }

  async function openMemory() {
    if (!result) return;
    setPeekLoading(true);
    try {
      setPeekMemory(await api.annotation(result.wordId));
    } catch (memoryError) {
      setError(memoryError.message);
    } finally {
      setPeekLoading(false);
    }
  }

  async function startAnotherCycle() {
    setBusy(true);
    setError("");
    try {
      const started = await api.startCycle();
      setCycle(started.cycle);
      setResult(null);
      setPeekMemory(null);
      await loadQuestion(started.cycle.id);
    } catch (startError) {
      setError(startError.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="flex h-dvh items-center justify-center text-sm text-slate-400">正在准备循环…</div>;
  }

  if (error && !cycle) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
        <div className="flex gap-2">
          <button type="button" onClick={bootstrap} className="btn-ghost">
            重试
          </button>
          <Link to="/" className="btn-primary">
            返回今日
          </Link>
        </div>
      </div>
    );
  }

  if (finished && cycle) {
    const accuracy = cycle.size ? (cycle.correct / cycle.size) * 100 : 0;
    return (
      <div className="safe-top flex min-h-dvh flex-col px-4 pb-6 pt-4">
        <div className="card p-5 text-center">
          <p className="text-sm text-slate-500 dark:text-slate-400">循环完成</p>
          <p className="mt-1 text-4xl font-semibold text-indigo-600 dark:text-indigo-400">{formatPercent(accuracy)}</p>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            共 {cycle.size} 题 · 答对 {cycle.correct} · 答错 {cycle.size - cycle.correct}
          </p>
          {cycle.size - cycle.correct > 0 ? (
            <p className="mt-2 text-xs text-slate-400">答错的词下次循环会继续出现，直到熟练度超过 90</p>
          ) : (
            <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">全部答对，继续保持。</p>
          )}
        </div>

        {error ? <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}

        {reviewCards.length > 0 ? (
          <section className="mt-4 space-y-2">
            <div>
              <h2 className="text-sm font-medium text-slate-600 dark:text-slate-300">
                低分卡片回顾（熟练度 ≤ 30）
              </h2>
              <p className="text-xs text-slate-400">每张卡片点「已读」加 10 分，不点不加分。</p>
            </div>
            {reviewCards.map((card) => (
              <div key={card.wordId} className="card p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-lg font-semibold">
                      {card.term}
                      {card.pos ? (
                        <span className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-normal text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          {card.pos}
                        </span>
                      ) : null}
                    </p>
                    <p className="truncate text-sm text-slate-500 dark:text-slate-400">{card.meaning}</p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      熟练度 {Math.round(card.mastery)} · {card.masteryLabel}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => readCard(card.wordId)}
                    disabled={card.cardRead}
                    className={`shrink-0 rounded-xl border px-3 py-2 text-sm ${
                      card.cardRead
                        ? "border-emerald-200 text-emerald-600 dark:border-emerald-900 dark:text-emerald-400"
                        : "border-indigo-200 text-indigo-600 dark:border-indigo-800 dark:text-indigo-300"
                    }`}
                  >
                    {card.cardRead ? "已读 ✓" : "已读 +10"}
                  </button>
                </div>
                {card.memory ? (
                  <div className="mt-2">
                    <MemoryCard memory={card.memory} compact />
                  </div>
                ) : null}
              </div>
            ))}
          </section>
        ) : null}

        <div className="mt-5 space-y-2">
          <button type="button" onClick={startAnotherCycle} disabled={busy} className="btn-primary w-full">
            {busy ? "准备中…" : "再来一个循环"}
          </button>
          <Link to="/" className="btn-ghost w-full">
            返回今日
          </Link>
        </div>
      </div>
    );
  }

  if (!question) {
    return <div className="flex h-dvh items-center justify-center text-sm text-slate-400">加载中…</div>;
  }

  const answered = cycle?.answered ?? 0;
  const total = cycle?.size ?? 0;
  const progressPercent = total ? Math.round((answered / total) * 100) : 0;
  const memory = result?.memory || peekMemory;
  const isMastered = result?.action === "mastered";

  return (
    <div className="safe-top flex min-h-dvh flex-col">
      <div className="flex items-center gap-2 px-4 py-3">
        <Link
          to="/"
          aria-label="退出循环"
          className="flex h-10 w-10 items-center justify-center rounded-full text-slate-500 active:bg-slate-200 dark:text-slate-400 dark:active:bg-slate-800"
        >
          <IconBack className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <div className="mb-1 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>{MODE_LABELS[question.mode]}</span>
            <span>
              {Math.min(answered + 1, total)}/{total}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
            <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>
      </div>

      <div className="flex-1 px-4">
        <div className="card p-5">
          {question.mode === "en2cn" ? (
            <>
              <p className="text-3xl font-semibold tracking-tight">{question.prompt}</p>
              {question.phonetic ? <p className="mt-1 text-sm text-slate-400">{question.phonetic}</p> : null}
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">选择正确的中文释义</p>
            </>
          ) : (
            <>
              <p className="text-2xl font-semibold leading-snug">{question.prompt}</p>
              {question.wordPos ? (
                <p className="mt-1 text-xs text-slate-400">词性：{question.wordPos}</p>
              ) : null}
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">写出对应的英文单词</p>
            </>
          )}
        </div>

        {question.mode === "en2cn" ? (
          <div className="mt-4 space-y-2">
            {(question.options || []).map((option) => {
              let state = "idle";
              if (result) {
                if (option === result.correctAnswer) state = "correct";
                else if (option === result.userAnswer) state = "wrong";
                else state = "muted";
              }
              return (
                <OptionButton
                  key={option}
                  state={state}
                  disabled={Boolean(result) || busy}
                  onClick={() => submit("submit", option)}
                >
                  {option}
                </OptionButton>
              );
            })}
          </div>
        ) : (
          <form
            className="mt-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!result && draft.trim()) submit("submit", draft);
            }}
          >
            <input
              ref={inputRef}
              value={result ? result.userAnswer : draft}
              onChange={(event) => setDraft(event.target.value)}
              disabled={Boolean(result) || busy}
              placeholder="输入英文单词后回车"
              autoCapitalize="none"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              enterKeyHint="done"
              className="input text-center text-lg tracking-wide"
            />
            {!result ? (
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowHint((value) => !value)}
                  className="min-h-10 rounded-xl border border-slate-200 px-3 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400"
                >
                  提示
                </button>
                <button type="submit" disabled={!draft.trim() || busy} className="btn-primary flex-1">
                  提交
                </button>
              </div>
            ) : null}
            {showHint && !result ? <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{question.hint}</p> : null}
          </form>
        )}

        {!result ? (
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => submit("dont_know")}
              disabled={busy}
              className="min-h-11 rounded-xl border border-rose-200 text-sm text-rose-600 active:bg-rose-50 dark:border-rose-900 dark:text-rose-400 dark:active:bg-rose-950/40"
            >
              不会
            </button>
            <button
              type="button"
              onClick={() => submit("mastered")}
              disabled={busy}
              className="min-h-11 rounded-xl border border-emerald-200 text-sm text-emerald-700 active:bg-emerald-50 dark:border-emerald-900 dark:text-emerald-400 dark:active:bg-emerald-950/40"
            >
              已熟练
            </button>
          </div>
        ) : null}

        {result ? (
          <div className="mt-4 space-y-3">
            <div
              className={`rounded-xl border px-4 py-3 ${
                result.correct
                  ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40"
                  : "border-rose-200 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <p
                  className={`flex items-center gap-1 text-base font-medium ${
                    result.correct ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300"
                  }`}
                >
                  <IconCheck className="h-5 w-5" />
                  {isMastered ? "已标记为熟练" : result.correct ? "答对了" : "答错了"}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  熟练度 {Math.round(result.masteryBefore)} → {Math.round(result.masteryAfter)}
                </p>
              </div>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                {result.term}
                {result.pos ? (
                  <span className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    {result.pos}
                  </span>
                ) : null}
                <span className="mx-1 text-slate-300">·</span>
                {result.meaning}
              </p>
              {!result.correct ? (
                <p className="mt-1 text-sm text-rose-700 dark:text-rose-300">正确答案：{result.correctAnswer}</p>
              ) : null}
              {isMastered ? (
                <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-400">
                  {result.mode === "en2cn" ? "熟练度已设为 60（很熟档）" : "熟练度已设为 95，退出循环"}
                </p>
              ) : null}
              <p className="mt-1 text-xs text-slate-400">用时 {(result.responseMs / 1000).toFixed(1)} 秒</p>

              {result.mode === "cn2en" && result.action !== "mastered" ? (
                <div className="mt-3 border-t border-slate-200 pt-2 dark:border-slate-800">
                  <p className="mb-1.5 text-xs text-slate-500 dark:text-slate-400">写完了，再自评一下：</p>
                  <div data-enter-stays className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => chooseAdjust("fuzzy")}
                      disabled={adjustBusy || Boolean(adjustChoice)}
                      className={`min-h-10 rounded-lg border text-sm ${
                        adjustChoice === "fuzzy"
                          ? "border-amber-400 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-300"
                          : "border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                      }`}
                    >
                      模糊（回滚熟练度）
                    </button>
                    <button
                      type="button"
                      onClick={() => chooseAdjust("mastered")}
                      disabled={adjustBusy || Boolean(adjustChoice)}
                      className={`min-h-10 rounded-lg border text-sm ${
                        adjustChoice === "mastered"
                          ? "border-emerald-400 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
                          : "border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                      }`}
                    >
                      已熟练（提到 95）
                    </button>
                  </div>
                  {adjustMessage ? (
                    <p className="mt-1.5 text-xs text-emerald-600 dark:text-emerald-400">{adjustMessage}</p>
                  ) : null}
                </div>
              ) : null}
            </div>

            {memory ? (
              <MemoryCard
                memory={memory}
                mark={result.userMark}
                onMark={result.mode === "en2cn" ? mark : undefined}
              />
            ) : (
              <button type="button" onClick={openMemory} disabled={peekLoading} className="btn-ghost w-full">
                {peekLoading ? "加载中…" : "看记忆卡片（词根 / 词缀 / 同根词）"}
              </button>
            )}
          </div>
        ) : null}
      </div>

      <div className="safe-bottom sticky bottom-0 mt-3 bg-gradient-to-t from-slate-50 via-slate-50 px-4 pb-3 pt-3 dark:from-slate-950 dark:via-slate-950">
        {result ? (
          <div>
            <button type="button" onClick={next} className="btn-primary w-full">
              {result.cycleFinished ? "查看结果" : "下一题"}
              <IconRight className="h-5 w-5" />
            </button>
            <p className="mt-1.5 text-center text-xs text-slate-400">按回车继续</p>
          </div>
        ) : (
          <p className="text-center text-xs text-slate-400">
            {question.mode === "en2cn" ? "点选一个释义即可作答" : "输入后按回车提交"}
          </p>
        )}
      </div>
    </div>
  );
}
