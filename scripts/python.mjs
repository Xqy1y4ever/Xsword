// 解析 Python 解释器路径，供 scripts/*.mjs 使用。
// 顺序：环境变量 PYTHON → 项目 .venv → 用户目录下 conda 环境 xcclient → PATH 中的 python。
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";

export function resolvePython() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push(process.env.PYTHON);
  candidates.push(
    path.join(process.cwd(), ".venv", "Scripts", "python.exe"),
    path.join(process.cwd(), ".venv", "bin", "python"),
    path.join(os.homedir(), ".conda", "envs", "xcclient", "python.exe"),
    path.join(os.homedir(), ".conda", "envs", "xcclient", "bin", "python")
  );
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  return "python";
}

/** 给 child_process 的 error 事件用：解释器找不到时输出可读提示。 */
export function reportPythonError(python, error) {
  console.error(`启动 Python 失败（${python}）：${error.message}`);
  console.error("请安装 Python 3.13，或设置环境变量 PYTHON 指向解释器（例如 conda 环境 xcclient）。");
  process.exit(1);
}
