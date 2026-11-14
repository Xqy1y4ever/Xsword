#!/usr/bin/env node
// 生产服务冒烟测试：验证静态页面、鉴权、循环流程、两种题型判分、词根与统计。
import process from "node:process";

const BASE = process.argv[2] || process.env.BASE_URL || "http://127.0.0.1:3000";
const PASSWORD = process.env.PASSWORD || process.argv[3] || "";
if (!PASSWORD) {
  console.error("缺少登录口令：请用环境变量 PASSWORD 提供，例如");
  console.error("  PowerShell:  $env:PASSWORD='你的口令'; node scripts/smoke.mjs");
  console.error("  Bash:        PASSWORD='你的口令' node scripts/smoke.mjs");
  process.exit(1);
}

let cookie = "";
const results = [];

function record(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  ${detail}` : ""}`);
}

async function request(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (cookie) headers.Cookie = cookie;
  const response = await fetch(BASE + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: "manual",
  });
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) cookie = setCookie.split(";")[0];
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : await response.text();
  return { status: response.status, data, type };
}

async function main() {
  const health = await request("/api/health");
  record("GET /api/health", health.status === 200 && health.data.ok === true, `llm=${health.data.llmEnabled}`);

  const page = await request("/");
  record(
    "GET / 返回前端页面",
    page.status === 200 && page.type.includes("text/html") && page.data.includes('id="root"'),
    `${Buffer.byteLength(String(page.data))} bytes`
  );

  const anonymous = await request("/api/today");
  record("未登录访问 /api/today 返回 401", anonymous.status === 401);

  const login = await request("/api/auth/login", { method: "POST", body: { password: PASSWORD } });
  record("POST /api/auth/login", login.status === 200 && Boolean(cookie), `status=${login.status}`);

  const today = await request("/api/today");
  record(
    "GET /api/today",
    today.status === 200 && today.data.totalWords > 0,
    `可练 ${today.data.eligibleCount} · 每循环 ${today.data.settings.cycleSize} 词 · 今日循环 ${today.data.today.cycles}`
  );

  const settings = await request("/api/settings");
  record("GET /api/settings", settings.status === 200 && settings.data.cycleSize > 0, `cycleSize=${settings.data.cycleSize}`);

  const started = await request("/api/cycle/start", { method: "POST", body: {} });
  const cycle = started.data.cycle;
  record("POST /api/cycle/start", started.status === 200 && Boolean(cycle), `循环 #${cycle && cycle.id} · ${cycle && cycle.size} 题`);

  let answeredOk = false;
  let dontKnow = null;
  for (let index = 0; index < Math.min(3, cycle.size); index += 1) {
    const next = await request(`/api/cycle/${cycle.id}/next`);
    if (next.data.finished) break;
    const question = next.data.question;
    if (index === 0) {
      const word = await request(`/api/words/${question.wordId}`);
      const answer = question.mode === "en2cn" ? word.data.meaning : word.data.term;
      const graded = await request(`/api/cycle/${cycle.id}/answer`, {
        method: "POST",
        body: { wordId: question.wordId, answer, responseMs: 1200, action: "submit" },
      });
      record(
        `POST /api/cycle/answer（${question.mode} 正确作答）`,
        graded.status === 200 && graded.data.correct === true,
        `熟练度 ${graded.data.masteryBefore} → ${graded.data.masteryAfter}`
      );
      answeredOk = graded.data.correct === true;
    } else if (index === 1) {
      const graded = await request(`/api/cycle/${cycle.id}/answer`, {
        method: "POST",
        body: { wordId: question.wordId, responseMs: 400, action: "dont_know" },
      });
      dontKnow = graded.data;
      record(
        "POST /api/cycle/answer（不会）",
        graded.status === 200 && graded.data.correct === false && graded.data.userMark === 1,
        `记忆卡片=${graded.data.showMemory}`
      );
    } else {
      const graded = await request(`/api/cycle/${cycle.id}/answer`, {
        method: "POST",
        body: { wordId: question.wordId, responseMs: 500, action: "mastered" },
      });
      record(
        "POST /api/cycle/answer（已熟练）",
        graded.status === 200 && [60, 95].includes(graded.data.masteryAfter),
        `mode=${graded.data.mode} → ${graded.data.masteryAfter}`
      );
    }
  }
  record("循环答题流程", answeredOk && Boolean(dontKnow));

  const roots = await request("/api/roots");
  record("GET /api/roots", roots.status === 200 && roots.data.total > 0, `${roots.data.total} 个词根`);

  const affixes = await request("/api/affixes?type=suffix");
  record("GET /api/affixes", affixes.status === 200 && affixes.data.items.length > 0, `${affixes.data.items.length} 个后缀`);

  const annotatedWords = await request("/api/words?annotation=ok&pageSize=1");
  if (annotatedWords.data && annotatedWords.data.items.length > 0) {
    const sample = annotatedWords.data.items[0];
    const memory = await request(`/api/words/${sample.id}/annotation`);
    record(
      "GET /api/words/{id}/annotation 记忆卡片",
      memory.status === 200 && Boolean(memory.data.mnemonic),
      memory.data.term || ""
    );
  } else {
    record("GET /api/words/{id}/annotation 记忆卡片", true, "词库暂无标注，跳过");
  }

  const stats = await request("/api/stats");
  record(
    "GET /api/stats",
    stats.status === 200 && stats.data.totals.seen > 0,
    `累计答题 ${stats.data.totals.seen} · 累计循环 ${stats.data.totals.cycles} · 连续 ${stats.data.streak} 天`
  );

  const missing = await request("/api/words?annotation=missing&pageSize=5");
  record("GET /api/words?annotation=missing", missing.status === 200, `未标注 ${missing.data.total}`);

  const failed = results.filter((item) => !item.ok);
  console.log(`\n${results.length - failed.length}/${results.length} 项通过`);
  if (failed.length > 0) process.exitCode = 1;
}

main().catch((error) => {
  console.error("冒烟测试异常：", error);
  process.exitCode = 1;
});
