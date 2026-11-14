# 部署到云服务器

两种方式任选：**Docker Compose（推荐）** 或 **conda + systemd**。都假设服务器是 Ubuntu 22.04/24.04，已放行 80/443（以及用于调试的 22）。

> 提醒：应用是单用户口令登录，不开放注册。请务必设置强口令，API 不要直接开到公网裸端口，前面挂上 HTTPS 反代。

---

## 一、准备

1. 域名（可选）：把 `vocab.example.com` 的 A 记录指向服务器公网 IP；没有域名也可先用 `http://IP:3000` 调试，但正式使用建议配 HTTPS。
2. 本地 `src/` 目录上传到服务器（二选一）：
   - `scp -r src user@server:/opt/vocab-app`（排除 `node_modules/`、`.npm-cache/`、`data/`、`dist/`）
   - 或先在本地打包：`tar czf vocab-app.tgz --exclude node_modules --exclude .npm-cache --exclude data --exclude dist .`

---

## 二、方式 A：Docker Compose（推荐）

### 1. 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # 重新登录后生效
```

### 2. 准备配置

```bash
cd /opt/vocab-app
cp .env.example .env
# 生成会话密钥
openssl rand -hex 32            # 填入 SESSION_SECRET
# 生成口令哈希（在容器外需要 Python 环境；也可以用下面「方式 B」的 python 执行，
# 或者把明文口令临时写进 .env 之外的命令里，在容器内生成后复制回来）
```

如果没有本地 Python 环境，可先构建镜像后在容器内生成：

```bash
docker compose build
docker compose run --rm --entrypoint python app -m app.cli.set_password '你的强口令'
# 把输出的 ADMIN_PASSWORD_HASH=... 复制进 .env
```

编辑 `.env`，至少确认：

```
ADMIN_PASSWORD_HASH=scrypt$...
SESSION_SECRET=<32 字节十六进制>
COOKIE_SECURE=0        # 接上 HTTPS 后改成 1
```

### 3. 启动

```bash
mkdir -p data
docker compose up -d
docker compose ps          # 等待 healthy
curl http://127.0.0.1:3000/api/health
```

### 4. 初始化词库（首次）

镜像里带了 `seed/`，数据库在 `./data` 卷里是空的，执行一次导入：

```bash
docker compose exec app python -m app.cli.init_seed
# 输出 wordsAdded=811 等统计（笔记词 162 + A 级词 569 + Word 词表 268，重复自动跳过）
```

也可以不导入，登录后在「词库 → 导入」页自己粘贴词表。

### 5. 配置词源标注模型（可选）

模型接口不再写在 `.env`，而是存在数据库里：

1. 浏览器登录应用，进入「设置 → 词源标注模型」；
2. 填 Base URL（如 `https://api.deepseek.com/v1`）、模型名（如 `deepseek-chat`）、API Key，点「保存配置」；
3. 点「测试连接」，返回「连接成功（xxx ms）」即配置生效；
4. 之后新增/导入的词会自动拆解词根词缀；不配置也不影响背单词与已预置的标注。

也可以直接用 API 写入（登录 Cookie 或接口文档 `/api/docs` 里操作）：

```bash
curl -X PUT http://127.0.0.1:3000/api/llm-config \
  -H 'Content-Type: application/json' -b cookie.txt \
  -d '{"baseUrl":"https://api.deepseek.com/v1","model":"deepseek-chat","apiKey":"sk-..."}'
```

数据卷备份会一并保存模型配置（含 Key）；如果不想让 Key 进入备份，在 `data/app.db` 层面自行处理即可。

### 6. 配置 HTTPS（二选一）

**Caddy（最简单，自动证书）**

```bash
cp deploy/Caddyfile.example Caddyfile
# 编辑 Caddyfile，把域名换成你的
docker compose --profile tls up -d
```

**nginx + certbot**

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/vocab
# 编辑域名与证书路径
sudo ln -s /etc/nginx/sites-available/vocab /etc/nginx/sites-enabled/vocab
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d vocab.example.com
```

HTTPS 生效后把 `.env` 的 `COOKIE_SECURE` 改为 `1`，然后 `docker compose up -d` 重启。

### 7. 常用运维

```bash
docker compose logs -f app          # 日志
docker compose restart app          # 重启
docker compose pull && docker compose up -d --build   # 更新代码后重建
# 备份：直接备份数据卷所在目录
tar czf backup-$(date +%F).tgz data
# 或在页面「导入导出」里导出 words.json
```

---

## 三、方式 B：conda + systemd（不用 Docker）

1. 安装 Miniconda（若服务器已有 conda 可跳过），创建环境：

```bash
conda create -n xcclient python=3.13 -y
conda activate xcclient
cd /opt/vocab-app
pip install -r backend/requirements.txt
```

2. 构建前端（需要 Node 20+）：

```bash
node -v || (curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs)
npm install
npm run build
```

3. 配置 `.env`（同方式 A 第二步），生成口令哈希：

```bash
python -m app.cli.set_password '你的强口令' --write
# 若提示找不到模块：export PYTHONPATH=/opt/vocab-app/backend
```

4. 初始化数据：

```bash
python -m app.cli.init_seed
```

5. 配置词源标注模型（可选）：同方式 A 第 5 步，登录后在「设置 → 词源标注模型」填写并测试连接。

6. 注册 systemd 服务：

```bash
sudo useradd -r -m -s /bin/bash vocab || true
sudo chown -R vocab:vocab /opt/vocab-app
sudo cp deploy/vocab.service /etc/systemd/system/vocab.service
# 按实际路径修改 ExecStart 里的 python 路径（conda 环境路径）
sudo systemctl daemon-reload
sudo systemctl enable --now vocab
sudo systemctl status vocab
curl http://127.0.0.1:3000/api/health
```

7. 反代与 HTTPS 同方式 A 第 6 步（nginx 指向 `127.0.0.1:3000`）。

---

## 四、验证清单

在服务器或本地执行：

```bash
curl -s http://127.0.0.1:3000/api/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/          # 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/api/today # 401（未登录）
```

再在浏览器/手机上打开站点，确认：

1. 能登录（口令为 `.env` 里配置的那个）；
2. 今日页显示计划进度；
3. 英→中、中→英各答一题，答错后出现记忆卡片；
4. 词库页能看到约 973 个单词（笔记词 + 南大 A 级词 + Word 词表）、词根库有数据；
5. 今日页能开始新循环，答对/答错/「不会」/「已熟练」按钮都生效，答错后出现记忆卡片；
6. **设置页能保存模型配置并「测试连接」成功**（不配模型也可跳过）；配置后可批量补标注：
   `docker compose exec app python -m app.cli.annotate --missing 900`
7. 手机宽度下无横向滚动、输入框聚焦不放大页面。

也可以跑冒烟脚本（在能访问该地址的机器上）：

```bash
BASE_URL=https://你的域名 PASSWORD=你的口令 node scripts/smoke.mjs
```

---

## 五、安全与备份建议

- 口令至少 12 位；`.env` 权限设成 `600`，不要提交到 git。
- 只通过 443 对外提供；Docker 端口已绑定 `127.0.0.1`，不要改成 `0.0.0.0`。
- 备份策略：每天 `tar czf backup-$(date +%F).tgz data`，保留 7–30 天；或定期在页面导出 `words.json`。备份里包含 `app.db`，也就包含了大模型 API Key（存于 `llm_config` 表），请妥善保管备份文件。
- 更换模型 Key：在「设置 → 词源标注模型」里重新填写；旧 Key 直接覆盖，不需要改 `.env` 或重启。
- 升级：拉新代码 → `npm run build`（或 `docker compose build`）→ 重启服务。SQLite 迁移在启动时自动执行（`CREATE TABLE IF NOT EXISTS`）。
- 数据恢复：停止服务，把备份的 `app.db` 放回 `data/`，再启动。
