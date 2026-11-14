# 背单词（Vocab）

移动端优先的单用户背单词 Web 应用：**循环制**练习、按熟练度自动切换题型、词源记忆卡片、大模型标注流水线。
前端 React + Vite + Tailwind，后端 FastAPI + SQLite。

## 功能

- **词库管理**：增删改查、搜索、排序、分页、批量文本导入、JSON/CSV 导出、清空；单词带音标/词性/例句/标签/自评。
- **词源记忆卡片**：显示词性，词根/词缀拆解、组合释义、同根词、衍生词、易混词、一句话联想；点词根可看词族。
  答错、点「不会」或熟练度低于「认识」档时自动展开，熟练词折叠为「看记忆卡片」。
- **词源标注流水线**：新增/导入的词自动排队，由 OpenAI 兼容大模型逐个拆解；每次把已有词根库作为上下文，新词根/词缀增量入库，按词根形成词族。
  - **模型配置存在后端数据库里**，登录后到「设置 → 词源标注模型」填写 Base URL / API Key / 模型名，支持「测试连接」；接口只回传 Key 末四位，不写入 `.env`。
- **词库规模（当前 430 词）**：
  - Word 词表（unit 1-4 essentials、Vocabulary 10.11、10.21、10.28 等）**265 词**；
  - 课堂笔记 165 词（带完整词源标注）；
  - 南京大学《大学英语通用词汇》A 级 569 词**暂时下架**（`--with-nce` 可恢复导入）；合计 **430 词**，按单词去重。
  - 430 词均已由配置的大模型补全词源标注（词根库 500+、词缀库 160+）与词性（n. / v. / adj. …），记忆卡片可直接用。
- **界面预览**：今日循环页截图见 [docs/today.png](docs/today.png)。
- **鉴权**：单用户口令（scrypt 哈希）+ HMAC 签名 Cookie（HttpOnly/SameSite=Lax），登录失败限流。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 19、Vite 7、Tailwind 4、React Router 7（移动端优先，无组件库） |
| 后端 | FastAPI 0.162、uvicorn、pydantic-settings、httpx |
| 数据 | SQLite（标准库 `sqlite3`，WAL 模式） |
| 环境 | Python 3.13；Node 20+ |
| 部署 | Docker 多阶段构建 / systemd + conda / nginx 或 Caddy 反代 |

## 目录结构

```
src/
  client/            前端源码（pages 页面、components 组件、lib/api）
  backend/
    app/             FastAPI 应用（routes、scoring 熟练度、cycle 循环、etymology 词根、llm/pipeline 标注）
    tests/           pytest 测试（128 项）
    requirements.txt
  seed/
    words.json       课堂笔记词（162，附词源标注 annotations.json）
    nce_a.json       南京大学《大学英语通用词汇》A 级词（569，暂时下架，--with-nce 恢复）
    words_extra.json 笔记与 Word 词表新增词（268）
    roots.json       预置词根/词缀库
    pos.json         全部单词的词性映射（term → n. / v. / adj. …）
    tools/           extract_docs.py（doc/docx 提取）、build_wordlist.py（生成上面的词表）
    _meanings.json   新增词的中文释义源（人工补全）
  scripts/           启动、测试、冒烟、Python 转发脚本
  deploy/            nginx / Caddy / systemd 示例
  data/              SQLite 数据（gitignored，首次运行生成）
  Dockerfile  docker-compose.yml  DEPLOY.md
```

## 本地运行

前置：Node 20+、Python 3.13（conda 环境或 venv 均可）。

`scripts/*.mjs` 会自动找 Python 解释器：`PYTHON` 环境变量 → 项目内 `.venv` → 用户目录下的 conda 环境 → PATH 里的 `python`。

```powershell
# 0. 准备配置文件
Copy-Item .env.example .env      # macOS/Linux: cp .env.example .env

# 1. 安装后端依赖
python -m pip install -r backend/requirements.txt

# 2. 安装前端依赖（npm 缓存重定向到项目内 .npm-cache）
npm install

# 3. 生成登录口令与会话密钥（自动写入 .env）
npm run set-password -- 你的口令 --write

# 4. 导入词库（默认导入笔记词 + Word 词表，共 430 词；A 级词表默认不导入）
npm run seed
#    只想追加词、不动已有标注时：
#    node scripts/py.mjs -m app.cli.init_seed --no-annotations
#    需要恢复南大 A 级词表时：
#    node scripts/py.mjs -m app.cli.init_seed --with-nce

# 5. 开发模式（Vite 5173 + API 3000）
npm run dev

# 或生产方式：先构建再启动（单端口 3000）
npm run build
npm start
```

- 本机访问：<http://127.0.0.1:3000>
- 手机访问：同一 Wi-Fi 下 `http://<本机局域网 IP>:3000`（首次可能需要在 Windows 防火墙放行 Node/3000 端口）
- 登录口令即第 3 步设置的口令；`.env` 里 `ADMIN_PASSWORD_HASH` 为空时登录返回 503。

其他命令：

```powershell
npm test                                  # 后端 pytest（128 项）
$env:PASSWORD='你的口令'; node scripts/smoke.mjs   # 对已启动服务冒烟
npm run annotate -- --limit 20            # 处理排队中的标注任务
node scripts/py.mjs -m app.cli.annotate --missing 900   # 给还没标注的词批量补标注
node scripts/py.mjs -m app.cli.pos --export             # 给缺词性的词补词性，并导出 seed/pos.json
node scripts/py.mjs -m seed.tools.build_wordlist        # 重新生成 A级/Word 词表种子（需先跑提取）
```

## 上传到 GitHub

仓库已包含 `.gitignore`：`.env`、`data/`（SQLite 与备份）、`node_modules/`、`dist/`、缓存等都不会提交，可以直接推送。

```powershell
git init -b main
git add .
git commit -m "Initial commit: 背单词 Web 应用"
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

> 新机器克隆后需要：`cp .env.example .env` → 安装依赖 → `npm run set-password -- 口令 --write` → `npm run seed`；大模型 Key 在「设置 → 词源标注模型」里重新填写（只存在本地数据库，不会进仓库）。

## 配置（.env）

| 变量 | 说明 |
|---|---|
| `HOST` / `PORT` | 监听地址与端口，默认 `0.0.0.0:3000` |
| `DB_PATH` | SQLite 文件路径，默认 `./data/app.db` |
| `SESSION_SECRET` | 会话签名密钥，`openssl rand -hex 32` 或 `npm run set-password --write` 自动生成 |
| `ADMIN_PASSWORD_HASH` | 登录口令的 scrypt 哈希 |
| `SESSION_TTL_DAYS` | 登录有效期，默认 30 天 |
| `COOKIE_SECURE` | HTTPS 部署时设为 `1` |
| `TIMEZONE` | 计划使用的时区，默认 `Asia/Shanghai` |

> 大模型接口（Base URL / API Key / 模型名 / 单批词数）不再放 `.env`，而是存在数据库 `llm_config` 表里，登录后在「设置 → 词源标注模型」维护，或调用 `GET|PUT /api/llm-config`、`POST /api/llm-config/test`。`.env` 里的 `LLM_*` 只在首次启动、数据库还没有配置行时导入一次（老部署兼容），之后以数据库为准。
> 每循环词数与选义比例存在数据库 `cycle_settings` 表里（`size`、`choice_ratio`），可在设置页或 `PUT /api/settings` 修改（`{"cycleSize": 100, "choiceRatio": 0.6}`）。

## 练习规则

- **一个循环 = 用户设定词数的一批题目**（默认 20，可在设置页调整）。循环内单词不重复；一天可以完成任意多个循环。
- **题型比例可调**：设置页可调选义/拼写比例（默认 **60% 选义 / 40% 拼写**，范围 0–100%）；每类题目数量按比例**四舍五入**，再受熟练度门槛限制（见下），不够时按可出的题型补齐。
- **题型门槛**：
  - 熟练度 **> 50** 才可能出拼写（≤50 只出选义）；
  - 熟练度 **> 60** 不再出释义（50–60 两种都可能）；
  - 熟练度 **> 90** 不再进入循环。
- **不连续重复**：同一个词如果连续两轮都出现，第三轮会被跳过（本轮不可选），断一轮后恢复资格。
- **选词顺序**：熟练度越低越先被选（两个题型池都按熟练度升序，同分随机）。
- **分数与自评（选义四档）**：
  | 自评 | 分数 |
  |---|---|
  | 不认识 | 15 |
  | 模糊 | 30 |
  | 认识 | 45 |
  | 很熟 | 60 |
- **首次见到一个单词（seen=0）**：
  - 答错 / 点「不会」→ **15**（不认识档）；
  - **3 秒内答对** → **45**（认识档）；
  - **3 秒外答对** → **30**（模糊档）。
- **之后的答题**：答对 **+15**、答错 **−15**（阶段边界间距就是 15，所以每次最多只跨一个阶段）。
- **每题都有「不会」和「已熟练」两个按钮**：
  - 不会：按答错处理；
  - 已熟练：选义题 → **60**（很熟档）；拼写题 → **95**（退出循环）。
- **拼写题写完后追加自评**：无论对错都会出现「模糊」和「已熟练」两个选项——
  - 模糊：把熟练度**回滚到本题作答前**的值；
  - 已熟练：直接把熟练度提到 **95**（>90，退出循环）。
  拼写题没有四档自评按钮。
- **自评标记直接改分数**：在词库/记忆卡片里点自评，立即把熟练度设为 15 / 30 / 45 / 60。
- **循环结束后的低分回顾**：本轮里熟练度 **≤30** 的卡片会再列一遍，点「已读」每张 **+10 分**（不点不加；每轮每张只加一次）。
- **快捷键**：答完一题后按 **回车** 进入下一题；拼写题输入框里的回车仍是提交答案，输入法组词中的回车不触发；焦点在「模糊 / 已熟练」按钮上时回车触发该按钮。
- 熟练度 **> 90** 的词不再进入循环；循环结束后可立刻开始下一轮。

## 熟练度结算

```
自评四档（选义）：不认识 15 / 模糊 30 / 认识 45 / 很熟 60
显示分数段：0–22.5 不认识 / 22.5–37.5 模糊 / 37.5–52.5 认识 / >52.5 很熟
题型比例：选义/拼写按设置的比例分配（默认 60/40），数量四舍五入；熟练度低的词优先被选
排除：>90 不再进入循环

首次作答（seen=0）：
  答错或「不会」→ 15（自评=1，不认识）
  3 秒内答对   → 45（自评=3，认识）
  3 秒外答对   → 30（自评=2，模糊）

之后的作答：
  答对：+15（最多跨一个阶段）
  答错：-15（最多跨一个阶段）

自评按钮：直接把熟练度设为 15 / 30 / 45 / 60
「已熟练」：选义题 → 60；拼写题（答题前）→ 95（退出循环）
拼写题答题后追加自评（对错都有）：
  「模糊」→ 回滚到本题作答前的熟练度
  「已熟练」→ 提到 95（>90，退出循环）
循环结束回顾：熟练度 ≤30 的卡片再展示；点「已读」每张 +10（每轮每张一次）
```

验收示例见 `backend/tests/test_scoring.py`；循环、60/40 分配与回顾卡片见 `backend/tests/test_cycle.py`。

## API 概览

`/api/auth/login|logout|me`、`/api/settings`、`/api/today`、`/api/cycle/start`、`/api/cycle/current`、`/api/cycle/{id}/next`、`/api/cycle/{id}/answer`、`/api/cycle/{id}/adjust`（拼写题模糊/已熟练）、`/api/cycle/{id}/abandon`、`/api/cycle/{id}/review-cards`、`/api/cycle/{id}/cards/{word_id}/read`、
`/api/words`（CRUD/import/export/purge/mark/annotation）、`/api/annotate`（触发标注/离线导入/状态）、`/api/llm-config`（模型配置读写/测试）、
`/api/roots`、`/api/affixes`、`/api/stats`、`/api/health`。接口文档：登录后访问 `/api/docs`。

## 部署

见 [DEPLOY.md](DEPLOY.md)：Docker Compose（推荐）或 conda + systemd，附 nginx/Caddy 的 HTTPS 配置。

## 已知限制

- 单用户、单词库、中文界面；不做多用户/多词书/音频发音/PWA 离线/FSRS 间隔重复。
- 反应时间由客户端上报（单用户场景不做防作弊），服务端只做范围钳制。
- 新导入的 A 级/Word 词默认没有词源标注（记忆卡片显示「暂无词源标注」）；配置大模型后可批量补标注，或只保留释义练习。
- 熟练度按循环开始时的值分配题型；循环进行中熟练度变化不会改变本轮题型。
- 修改每循环词数不会打断当前循环，下一轮生效。
