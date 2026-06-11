# jack门

> 新老互助破冰 — 基于性格问卷匹配的校园服务板块。
> 目标：一键上线 i大工。

---

## 这是什么

大一新生入学后信息不对称、社交壁垒高。通过 12 题性格问卷，把「能帮人的老生」和「需要帮的新生」撮合到一起。

**不是交友匹配，是互助匹配。**

核心逻辑：
- 性格相似 → 容易聊起来（同频）
- 能力互补 → 帮得上忙（你的短板恰好是对方的长处）

---

## 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| 前端 | 纯 HTML/CSS/JS | 3 个页面，不需要框架。一个学生项目不值得上 React。 |
| 后端 | Python FastAPI | 用户已熟 Python，FastAPI 学习成本接近零。 |
| 数据库 | Supabase (PostgreSQL) | 免费 500MB，自动生成 REST API，省掉 ORM。 |
| 部署 | Vercel（前端）+ Railway（后端）| 都是白嫖额度，够跑一个校园小服务。 |

---

## 项目结构

```
jackmen/
├── README.md              # 你在这
├── frontend/              # 前端 H5
│   ├── index.html         # 首页：身份选择（新生/老生）
│   ├── quiz.html          # 问卷页：12 题性格评估
│   ├── match.html         # 结果页：匹配 Top-3 + 匹配理由
│   ├── style.css          # 移动端优先的样式
│   └── app.js             # 前端逻辑（表单提交、结果渲染）
├── backend/               # 后端 API
│   ├── main.py            # FastAPI 入口 + 路由
│   ├── match.py           # 匹配算法核心
│   ├── models.py          # 数据模型（Pydantic）
│   ├── requirements.txt   # Python 依赖
│   └── .env.example       # 环境变量模板
└── supabase/              # 数据库
    └── schema.sql         # 建表语句
```

---

## 问卷设计

共 12 题，每题 4 选 1。8 题 MBTI 性格画像，4 题互助行为评估。

### MBTI 四维（每维 2 题）

| 维度 | 含义 | 示例题目 |
|------|------|---------|
| E/I | 能量来源（外向/内向）| "上了一天课，晚上更想约朋友 vs 自己待着" |
| S/N | 信息获取（感觉/直觉）| "学新东西更依赖具体步骤 vs 抽象框架" |
| T/F | 决策方式（思考/情感）| "做决定优先逻辑数据 vs 感受价值观" |
| J/P | 生活方式（判断/感知）| "面对截止日期提前规划 vs 截止前冲刺" |

### 互助行为评估（4 题）

| 题号 | 维度 | 用途 |
|------|------|------|
| 9 | 擅长帮助领域 | 互补匹配：你的短板 = 对方的长处 |
| 10 | 求助习惯 | 匹配主动型 vs 被动型 |
| 11 | 协作偏好（带节奏 vs 跟节奏）| 互补配对 |
| 12 | 愿意帮助什么样的人 | 调优匹配的软偏好 |

---

## 匹配算法 V1

输入：12 维向量（每题映射为数值编码）
输出：Top-3 匹配 + 匹配理由

### 两条规则

**规则1：互补匹配（权重 0.6）**
- 第 9 题（擅长领域）≠ 对方第 10 题方向 → 你能帮他
- 第 11 题 A 型（带节奏）+ B 型（跟节奏） → 天然互补

**规则2：相似匹配（权重 0.4）**
- E/I、T/F、J/P 同向 → 沟通同频、节奏一致

### 匹配理由生成

模板化，不需要 LLM：

```
"你们都偏好[直觉型/感觉型]学习，沟通会很顺畅。
 另外你在[学习方法]方面可以帮到对方。"
```

---

## API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/submit` | 提交问卷，返回 user_id |
| GET | `/match/{user_id}` | 获取匹配结果 Top-3 |
| GET | `/pool` | 查看当前可匹配人数 |
| GET | `/health` | 健康检查 |

### POST /submit

```json
// Request
{
  "role": "freshman",       // "freshman" | "senior"
  "answers": [0, 2, 1, 3, 0, 1, 2, 0, 1, 3, 0, 2],
  "contact": "@wechat_id"   // 匹配后展示给对方
}

// Response
{
  "user_id": "uuid-xxx",
  "message": "已提交，当前池子有 12 人，等待匹配..."
}
```

### GET /match/{user_id}

```json
// Response
{
  "user_id": "uuid-xxx",
  "matches": [
    {
      "score": 0.85,
      "reason": "你们都偏好直觉型学习，沟通会很顺畅。另外对方在[学习方法]方面可以帮到你。",
      "contact": "@senior_wechat"
    },
    ...
  ]
}
```

---

## 快速开始（本地开发）

```bash
# 1. 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 2. 前端（另开终端）
cd frontend
python3 -m http.server 3000

# 3. 浏览器打开 http://localhost:3000
```

---

## 部署

| 环境 | 命令/操作 |
|------|---------|
| 前端 | `cd frontend && vercel --prod` |
| 后端 | `cd backend && railway up` |
| 数据库 | 在 Supabase 控制台执行 `schema.sql` |

---

## 开发阶段

- [ ] Phase 1：本地跑通（问卷 + 匹配算法 + API）
- [ ] Phase 2：部署 Vercel + Railway + Supabase
- [ ] Phase 3：联系 i大工 运营方，接板块入口
- [ ] Phase 4：GitHub Actions 一键发布

---

## 注意事项

- 不做头像/昵称/聊天功能 — 匹配后展示微信号，让用户自己聊。减少开发量。
- 不做复杂 UI — 移动端表单足够用，i大工用户都在手机上打开。
- 隐私：问卷结果不公开，仅对匹配对象展示匹配理由。
- 冷启动：先拉 10-20 个熟人填，池子跑起来再正式推广。
