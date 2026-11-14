#!/usr/bin/env node
// 启动 FastAPI 服务（uvicorn）。--reload 用于开发。
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { reportPythonError, resolvePython } from "./python.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = resolvePython();

function readEnvFile() {
  const file = path.join(root, ".env");
  const out = {};
  if (!existsSync(file)) return out;
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/.exec(line);
    if (m && !line.trim().startsWith("#")) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return out;
}

const fileEnv = readEnvFile();
const host = process.env.HOST || fileEnv.HOST || "0.0.0.0";
const port = process.env.PORT || fileEnv.PORT || "3000";
const reload = process.argv.includes("--reload");

const args = ["-m", "uvicorn", "app.main:app", "--host", host, "--port", String(port)];
if (reload) args.push("--reload", "--reload-dir", path.join(root, "backend"));

console.log(`[api] uvicorn http://${host}:${port}${reload ? " (reload)" : ""}`);

const child = spawn(python, args, {
  cwd: root,
  stdio: "inherit",
  env: {
    ...process.env,
    ...fileEnv,
    PYTHONPATH: path.join(root, "backend"),
    PYTHONUTF8: "1",
  },
});
child.on("exit", (code) => process.exit(code ?? 0));
child.on("error", (error) => reportPythonError(python, error));
