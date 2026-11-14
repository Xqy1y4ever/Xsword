#!/usr/bin/env node
// 用 Python 执行 app.cli.* 命令，并把 backend 加入 PYTHONPATH。
import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { reportPythonError, resolvePython } from "./python.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = resolvePython();

const args = process.argv.slice(2);
const child = spawn(python, args, {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: path.join(root, "backend"), PYTHONUTF8: "1" },
});
child.on("exit", (code) => process.exit(code ?? 0));
child.on("error", (error) => reportPythonError(python, error));
