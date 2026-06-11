# jack门 项目记录

> 新老互助破冰 — 基于性格问卷匹配的校园服务板块
> 目标：上线 i大工，解决新生入学信息不对称和社交壁垒

## 技术栈

| 层 | 选型 | 原因 |
|----|------|------|
| 前端 | 纯 HTML/CSS/JS | 3个页面不需要框架，移动端优先 |
| 后端 | Python FastAPI | 用户已熟 Python |
| 数据库 | Supabase (PostgreSQL) | 免费 500MB，自带 REST API |
| 部署 | Vercel（前端）+ Railway（后端） | 免费额度够校园小服务 |

## 核心设计

### 匹配算法

```
总分 = 互补分 × 0.6 + 相似分 × 0.4

互补分: 求助方向 == 对方擅长领域 (+0.6)
        + 协作风格互补（带节奏 vs 跟节奏）(+0.4)

相似分: MBTI 四维同向数 / 4
```

扫描池子所有人 → 算分 → 取 Top-3。

### 问卷设计（12 题）

- 8 题 MBTI 性格画像（E/I、S/N、T/F、J/P 各 2 题）
- 4 题互助行为评估（擅长领域、求助习惯、协作偏好、帮人倾向）

### 数据表

```
users:         id, role, answers[], contact, created_at
notifications: id, user_id, from_id, message, read, created_at
connections:   id, user_id, matched_id, status(connected/ignored), created_at
```

### API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /submit | 提交问卷 |
| GET | /match/{id} | 获取匹配（排除已忽略） |
| POST | /match/{id}/connect | 标记已连接 |
| POST | /match/{id}/ignore | 忽略此人（换一批） |
| GET | /notifications/{id} | 查看通知 |
| POST | /notifications/{id}/read | 标记已读 |
| GET | /pool | 池子统计 |
| GET | /admin/stats | 管理后台数据 |

## 功能清单

### 已实现
- 身份选择（新生/老生）
- 12 题问卷
- 匹配算法 Top-3 + 匹配理由
- 双向通知（被匹配方收到通知）
- 分享按钮（Web Share API + 剪贴板降级）
- 匹配冷却（忽略后排除、连接后不再出现）
- 换一批
- 返回导航
- 隐私说明页
- 数据持久化（Supabase，重启不丢）
- 管理后台统计

### 待接 i大工
- SSO 身份认证（学号/姓名）
- 隐私脱敏（姓+专业替代微信号）
- i大工消息推送
- 板块 URL 嵌入

## 项目结构

```
jackmen/
├── README.md
├── frontend/
│   ├── index.html     # SPA 三页合一
│   ├── style.css      # 深色主题移动端样式
│   └── app.js         # 前端逻辑
├── backend/
│   ├── main.py        # FastAPI 路由
│   ├── match.py       # 匹配算法
│   ├── models.py      # Pydantic 模型
│   ├── requirements.txt
│   └── .env           # Supabase 凭证
└── supabase/
    └── schema.sql     # 建表 + RLS 策略
```

## 本地运行

```bash
# 后端
cd backend
conda activate jackmen
uvicorn main:app --port 8000

# 前端（另开终端）
cd frontend
python3 -m http.server 3000

# 浏览器打开 http://localhost:3000
```

## 会话记录

### 2026-06-11
- 回顾 jackmen 项目目标（i大工板块、新老互助匹配）
- 创建 conda 环境 jackmen (Python 3.9)
- 后端四接口跑通（health/submit/match/pool）
- 前端三合一页面（首页/问卷/结果）
- 加分享按钮 + 双向通知系统
- 接 Supabase 持久化（三张表 + RLS 策略）
- 加匹配冷却：connect/ignore 状态 + connections 表
- 前端加返回导航 + 隐私页 + 连接/忽略按钮 + 空状态优化
