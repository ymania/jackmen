# Railway 部署指南 — jackmen 校园平台

## 前置条件

- GitHub 仓库 `ymania/jackmen` 已推送最新代码
- Railway 账号（直接用 GitHub 登录 https://railway.app）

---

## 第一步：部署 GitHub 仓库

1. 打开 [Railway Dashboard](https://railway.app/dashboard)
2. 点 **New Project** → **Deploy from GitHub repo**
3. 授权 Railway 访问 GitHub → 选 `ymania/jackmen`
4. Railway 读取 `railway.json` → 识别 `"root": "backend"` → 在 `backend/` 目录找 `requirements.txt` → 开始构建

> 构建过程：Nixpacks 以 `backend/` 为项目根 → `pip install -r requirements.txt` → 安装 FastAPI / uvicorn / psycopg2 等

---

## 第二步：添加 PostgreSQL 数据库

1. 项目创建后，在项目页面点 **New** → **Database** → 选 **PostgreSQL**
2. Railway 自动：
   - 创建 PostgreSQL 实例
   - 注入 `DATABASE_URL` 环境变量到你的应用
   - 触发重新部署

> `db.py` 检测到 `DATABASE_URL` → 自动走 PostgreSQL 模式（建表、种子数据全自动）

---

## 第三步：验证部署

等部署完成后，拿到域名（如 `jackmen-production.up.railway.app`）：

```bash
# 健康检查
curl https://你的域名.up.railway.app/health
# 应返回: {"status":"ok","db":"postgresql"}

# 测试匹配 API
curl https://你的域名.up.railway.app/api/pool
# 应返回: {"total":0,"freshmen":0,"seniors":0}
```

如果 `/health` 返回 `x-railway-fallback: true` 或 404 "Application not found"：
- 去 Railway → 点你的 service → **Deployments** 标签 → 看 **Build logs** 和 **Deploy logs**
- 常见问题见下方「故障排查」

---

## 第四步：连接前端

你的前端 HTML 里，把 API 地址从 `localhost:8000` 改成 Railway 域名：

```javascript
// frontend/app.js 或 index.html 中
const API_BASE = "https://你的域名.up.railway.app";
```

然后前端可以部署到 Vercel / Netlify / GitHub Pages（静态页面随便放哪都行）。

---

## 项目文件结构（Railway 需要的内容）

```
jackmen/                          ← GitHub 仓库根目录
├── railway.json                  ← Railway 配置（指定 root=backend）
└── backend/
    ├── main.py                   ← FastAPI 入口
    ├── db.py                     ← 数据库层（SQLite/PostgreSQL 自适应）
    ├── match.py                  ← 匹配算法
    ├── models.py                 ← Pydantic 模型
    ├── requirements.txt          ← Python 依赖
    └── (不需要 jackmen.db)       ← Railway 用 PostgreSQL，本地 DB 文件不需要
```

---

## 故障排查

### 症状：`x-railway-fallback: true`（应用没起来）

**原因1**：`railway.json` 没配置 `"root": "backend"`
- 已修复：`railway.json` 指定了构建根目录为 `backend/`，Nixpacks 会在那找 `requirements.txt`

**原因2**：构建失败（`uvicorn[standard]` 方括号语法）
- 已修复：`requirements.txt` 中去掉了 `[standard]` extras

**原因3**：PostgreSQL 连接失败导致整个应用崩溃
- 已修复：`db.py` 改为懒连接，不在 import 时连库。`/health` 端点永不死

**原因4**：Railway 免费额度用完了
- 免费计划每月 $5 额度。检查 Dashboard → Billing

### 症状：API 返回 500

看 Deploy logs 里的具体报错。通常是：
- PostgreSQL 还没就绪（等 30 秒重试）
- 表结构不匹配（Railway 会自动建表，不需要手动 migration）

### 症状：CORS 错误

已配置 `allow_origins=["*"]`，不应该出现。如果前端用 HTTPS 调后端 HTTP，Railway 自动升级到 HTTPS。

---

## 本地开发 vs 生产

| 环境 | 数据库 | 启动方式 |
|------|--------|----------|
| 本地 | SQLite (`backend/jackmen.db`) | `cd backend && uvicorn main:app --port 8000` |
| Railway | PostgreSQL（自动） | `railway.json` 里的 `startCommand` |

切换逻辑在 `db.py`：有 `DATABASE_URL` → PostgreSQL，没有 → SQLite。不需要改代码。
