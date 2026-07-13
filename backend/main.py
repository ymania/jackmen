"""
校园平台 — 统一后端
  匹配互助 + 刷题训练 + 论坛 + PDF资料

启动: cd backend && uvicorn main:app --port 8000 --host 0.0.0.0
"""
import uuid, hashlib, json
from typing import Optional
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from db import db, _IS_PG
if _IS_PG:
    from db import _pg_get_conn
from match import match as run_match
from models import (
    QuizSubmit, MatchResponse, MatchItem, PoolInfo,
    Notification, NotificationList, ConnectionAction,
    UserRegister, UserLogin,
    AnswerSubmit, StatsOut,
    ForumPostCreate, ForumCommentCreate,
)

app = FastAPI(title="校园平台", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def _conn():
    """返回统一连接 — PG 下自动转换 ? 占位符为 %s"""
    if _IS_PG:
        return _PgConn()
    return db._conn

class _PgConn:
    """PG 连接包装器，模拟 sqlite3.Connection 接口"""
    def execute(self, sql, params=None):
        import psycopg2.extras
        conn = _pg_get_conn()
        sql = sql.replace("?", "%s")
        # SQLite 特有语法转换
        sql = sql.replace("ORDER BY RANDOM()", "ORDER BY RANDOM()")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or [])
        return _PgCursor(cur)
    def commit(self):
        pass  # autocommit=True 不需要手动 commit

class _PgCursor:
    def __init__(self, cur):
        self._cur = cur
    def fetchone(self):
        row = self._cur.fetchone()
        return _PgRow(row) if row else None
    def fetchall(self):
        return [_PgRow(r) for r in self._cur.fetchall()]
    @property
    def lastrowid(self):
        # 需要在 INSERT 时加 RETURNING id
        return None

class _PgRow:
    def __init__(self, d):
        self._d = d
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._d.values())[key]
        return self._d[key]
    def keys(self):
        return self._d.keys()
    def __iter__(self):
        return iter(self._d.values())

def _parse_tags(item: dict) -> dict:
    tags = item.get("tags", [])
    if isinstance(tags, list):
        item["tags"] = tags
    elif isinstance(tags, str):
        try:
            item["tags"] = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            item["tags"] = []
    else:
        item["tags"] = []
    return item


# ══════════════════════ 健康 ══════════════════════
@app.get("/health")
def health():
    return {"status": "ok", "db": "postgresql" if _IS_PG else "sqlite"}


# ══════════════════════ 一、匹配系统 ══════════════════════

@app.post("/api/match/submit")
def match_submit(data: QuizSubmit):
    uid = str(uuid.uuid4())[:8]
    db.table("users").insert({
        "id": uid, "role": data.role,
        "answers": json.dumps(data.answers), "contact": data.contact,
    }).execute()
    fm = db.table("users").select("id", count="exact").eq("role", "freshman").execute().count
    sr = db.table("users").select("id", count="exact").eq("role", "senior").execute().count
    return {"user_id": uid, "message": f"已提交！池子 {fm+sr} 人（新生{fm}，老生{sr}）"}


@app.get("/api/match/{user_id}")
def match_get(user_id: str):
    u = db.table("users").select("*").eq("id", user_id).execute()
    if not u.data: raise HTTPException(404, "用户不存在")
    user = u.data[0]
    target = "senior" if user["role"] == "freshman" else "freshman"
    pool = db.table("users").select("*").eq("role", target).execute()
    conns = db.table("connections").select("matched_id,status").eq("user_id", user_id).execute()
    handled = {r["matched_id"] for r in conns.data if r["status"] in ("connected", "ignored")}
    candidates = [{"id": p["id"], "answers": p["answers"], "contact": p["contact"]}
                   for p in pool.data if p["id"] != user_id and p["id"] not in handled]
    if not candidates: return MatchResponse(user_id=user_id, matches=[])
    matches = run_match(user["answers"], candidates)
    label = "新生" if user["role"] == "freshman" else "老生"
    for m in matches:
        db.table("notifications").insert({
            "user_id": m["matched_id"], "from_id": user_id,
            "from_contact": user["contact"], "from_role": label,
            "message": f"一位{label}匹配到了你！", "read": 0,
        }).execute()
    return MatchResponse(user_id=user_id, matches=[MatchItem(**m) for m in matches])


@app.post("/api/match/{user_id}/connect")
def match_connect(user_id: str, body: ConnectionAction):
    ex = db.table("connections").select("*").eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    if ex.data:
        db.table("connections").update({"status": "connected"}).eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    else:
        db.table("connections").insert({"user_id": user_id, "matched_id": body.matched_id, "status": "connected"}).execute()
    return {"status": "ok"}


@app.post("/api/match/{user_id}/ignore")
def match_ignore(user_id: str, body: ConnectionAction):
    ex = db.table("connections").select("*").eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    if ex.data:
        db.table("connections").update({"status": "ignored"}).eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    else:
        db.table("connections").insert({"user_id": user_id, "matched_id": body.matched_id, "status": "ignored"}).execute()
    return {"status": "ok"}


@app.get("/api/notifications/{user_id}")
def notifications_get(user_id: str):
    u = db.table("users").select("id").eq("id", user_id).execute()
    if not u.data: raise HTTPException(404)
    nf = db.table("notifications").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    unread = sum(1 for n in nf.data if not n["read"])
    return NotificationList(user_id=user_id, unread=unread, notifications=[
        Notification(from_id=n["from_id"], from_contact=n.get("from_contact",""),
                     from_role=n.get("from_role",""), message=n["message"],
                     read=bool(n["read"]), time=n.get("created_at","")) for n in nf.data
    ])


@app.post("/api/notifications/{user_id}/read")
def notifications_read(user_id: str):
    db.table("notifications").update({"read": 1}).eq("user_id", user_id).eq("read", 0).execute()
    return {"status": "ok"}


@app.get("/api/pool")
def pool(): 
    fm = db.table("users").select("id", count="exact").eq("role", "freshman").execute().count
    sr = db.table("users").select("id", count="exact").eq("role", "senior").execute().count
    return PoolInfo(total=fm+sr, freshmen=fm, seniors=sr)


# ══════════════════════ 二、用户系统 ══════════════════════

@app.post("/api/register")
def register(body: UserRegister):
    if db.table("math_users").select("id").eq("email", body.email).execute().data:
        raise HTTPException(409, "邮箱已注册")
    uid = str(uuid.uuid4())
    db.table("math_users").insert({
        "id": uid, "email": body.email, "password_hash": _hash(body.password),
        "nickname": body.nickname or body.email.split("@")[0],
    }).execute()
    return {"id": uid, "email": body.email}


@app.post("/api/login")
def login(body: UserLogin):
    r = db.table("math_users").select("*").eq("email", body.email).execute()
    if not r.data: raise HTTPException(401, "邮箱或密码错误")
    u = r.data[0]
    if u["password_hash"] != _hash(body.password): raise HTTPException(401, "邮箱或密码错误")
    return {"id": u["id"], "email": u["email"], "nickname": u["nickname"],
            "membership": u["membership"], "membership_expires_at": u.get("membership_expires_at"),
            "created_at": u.get("created_at")}


@app.get("/api/user/{user_id}")
def user_get(user_id: str):
    r = db.table("math_users").select("*").eq("id", user_id).execute()
    if not r.data: raise HTTPException(404)
    return r.data[0]


# ══════════════════════ 三、题库 ══════════════════════
# 注意：/random 必须在 /{problem_id} 之前，否则 FastAPI 会把 "random" 当 int 解析

@app.get("/api/problems/random")
def problem_random(user_id: str = Query(...)):
    conn = _conn()
    done = [r[0] for r in conn.execute("SELECT problem_id FROM user_problem_status WHERE user_id=?", [user_id]).fetchall()]
    if done:
        ph = ",".join(["?"]*len(done))
        row = conn.execute(f"SELECT * FROM problems WHERE id NOT IN ({ph}) ORDER BY RANDOM() LIMIT 1", done).fetchone()
    else:
        row = conn.execute("SELECT * FROM problems ORDER BY RANDOM() LIMIT 1").fetchone()
    if not row:
        row = conn.execute("SELECT * FROM problems ORDER BY RANDOM() LIMIT 1").fetchone()
    return _parse_tags(dict(row)) if row else {}


@app.get("/api/problems/{problem_id}")
def problem_get(problem_id: int):
    conn = _conn()
    row = conn.execute("SELECT * FROM problems WHERE id=?", [problem_id]).fetchone()
    if not row: raise HTTPException(404)
    return _parse_tags(dict(row))


@app.get("/api/problems")
def problems_list(subject: Optional[str]=Query(None), difficulty: Optional[int]=Query(None),
                  keyword: Optional[str]=Query(None), page: int=Query(1,ge=1), page_size: int=Query(20,ge=1,le=100)):
    conn = _conn()
    cond, params = [], []
    if subject and subject != "全部科目": cond.append("subject=?"); params.append(subject)
    if difficulty: cond.append("difficulty=?"); params.append(difficulty)
    if keyword: cond.append("(title LIKE ? OR content LIKE ?)"); params.extend([f"%{keyword}%", f"%{keyword}%"])
    where = " WHERE " + " AND ".join(cond) if cond else ""
    total = conn.execute(f"SELECT COUNT(*) FROM problems{where}", params).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM problems{where} ORDER BY id LIMIT ? OFFSET ?",
                        params + [page_size, (page-1)*page_size]).fetchall()
    return {"data": [_parse_tags(dict(r)) for r in rows], "total": total, "page": page, "page_size": page_size}


@app.post("/api/problems/answer")
def problem_answer(body: AnswerSubmit):
    conn = _conn()
    ex = conn.execute("SELECT id FROM user_problem_status WHERE user_id=? AND problem_id=?", [body.user_id, body.problem_id]).fetchone()
    import datetime; now = datetime.datetime.now().isoformat()
    if ex:
        conn.execute("UPDATE user_problem_status SET status=?,wrong_reason=?,attempted_at=? WHERE id=?", [body.status, body.wrong_reason, now, ex[0]])
    else:
        conn.execute("INSERT INTO user_problem_status (user_id,problem_id,status,wrong_reason,attempted_at) VALUES (?,?,?,?,?)", [body.user_id, body.problem_id, body.status, body.wrong_reason, now])
    conn.commit()
    _update_rating(body.user_id, body.status)
    return {"ok": True}


@app.get("/api/user/{user_id}/wrong-problems")
def wrong_problems(user_id: str):
    rows = _conn().execute("""SELECT ups.id, ups.problem_id, ups.status, ups.wrong_reason, ups.marked, ups.attempted_at,
        p.title, p.subject, p.difficulty FROM user_problem_status ups
        JOIN problems p ON ups.problem_id=p.id WHERE ups.user_id=? AND ups.status='wrong' ORDER BY ups.attempted_at DESC""", [user_id]).fetchall()
    return [{"id":r[0],"problem_id":r[1],"status":r[2],"wrong_reason":r[3] or "","marked":bool(r[4]),"attempted_at":r[5],"title":r[6],"subject":r[7],"difficulty":r[8]} for r in rows]


@app.post("/api/user/wrong-problems/{record_id}/toggle-mark")
def toggle_mark(record_id: int):
    conn = _conn()
    cur = conn.execute("SELECT marked FROM user_problem_status WHERE id=?", [record_id]).fetchone()
    if not cur: raise HTTPException(404)
    conn.execute("UPDATE user_problem_status SET marked=? WHERE id=?", [0 if cur[0] else 1, record_id])
    conn.commit()
    return {"marked": not bool(cur[0])}


# ══════════════════════ 四、论坛 ══════════════════════

@app.get("/api/forum/categories")
def forum_categories():
    conn = _conn()
    cats = conn.execute("SELECT * FROM forum_categories ORDER BY sort_order").fetchall()
    return [{"id":c[0],"name":c[1],"slug":c[2],"post_count": conn.execute("SELECT COUNT(*) FROM forum_posts WHERE category_id=?",[c[0]]).fetchone()[0]} for c in cats]


@app.get("/api/forum/posts")
def forum_posts(category_id: Optional[int]=Query(None), page: int=Query(1,ge=1)):
    conn = _conn()
    cond, params = [], []
    if category_id: cond.append("fp.category_id=?"); params.append(category_id)
    where = " WHERE " + " AND ".join(cond) if cond else ""
    total = conn.execute(f"SELECT COUNT(*) FROM forum_posts fp{where}", params).fetchone()[0]
    rows = conn.execute(f"""SELECT fp.id, fp.category_id, fc.name, fp.user_id,
        COALESCE(mu.nickname,'匿名'), fp.title, fp.content, fp.created_at
        FROM forum_posts fp JOIN forum_categories fc ON fp.category_id=fc.id
        LEFT JOIN math_users mu ON fp.user_id=mu.id{where}
        ORDER BY fp.created_at DESC LIMIT 20 OFFSET ?""", params + [(page-1)*20]).fetchall()
    posts = []
    for r in rows:
        cc = conn.execute("SELECT COUNT(*) FROM forum_comments WHERE post_id=?",[r[0]]).fetchone()[0]
        posts.append({"id":r[0],"category_id":r[1],"category_name":r[2],"user_id":r[3],"user_nickname":r[4],"title":r[5],"content":r[6][:200],"comment_count":cc,"created_at":r[7]})
    return {"data":posts,"total":total}


@app.post("/api/forum/posts")
def forum_post_create(body: "ForumPostCreate"):
    conn = _conn()
    cur = conn.execute("INSERT INTO forum_posts (category_id,user_id,title,content) VALUES (?,?,?,?)",
                       [body.category_id, body.user_id, body.title, body.content])
    conn.commit()
    return {"id": cur.lastrowid, **body.model_dump()}


@app.get("/api/forum/posts/{post_id}")
def forum_post_get(post_id: int):
    conn = _conn()
    p = conn.execute("""SELECT fp.id,fp.title,fp.content,fc.name,COALESCE(mu.nickname,'匿名'),fp.created_at
        FROM forum_posts fp JOIN forum_categories fc ON fp.category_id=fc.id
        LEFT JOIN math_users mu ON fp.user_id=mu.id WHERE fp.id=?""", [post_id]).fetchone()
    if not p: raise HTTPException(404)
    comments = conn.execute("""SELECT fc.id,fc.content,COALESCE(mu.nickname,'匿名'),fc.created_at
        FROM forum_comments fc LEFT JOIN math_users mu ON fc.user_id=mu.id
        WHERE fc.post_id=? ORDER BY fc.created_at""", [post_id]).fetchall()
    return {"post":{"id":p[0],"title":p[1],"content":p[2],"category_name":p[3],"user_nickname":p[4],"created_at":p[5]},
            "comments":[{"id":c[0],"content":c[1],"user_nickname":c[2],"created_at":c[3]} for c in comments]}


@app.post("/api/forum/comments")
def forum_comment_create(body: "ForumCommentCreate"):
    conn = _conn()
    cur = conn.execute("INSERT INTO forum_comments (post_id,user_id,content) VALUES (?,?,?)",
                       [body.post_id, body.user_id, body.content])
    conn.commit()
    return {"id": cur.lastrowid, **body.model_dump()}


# ══════════════════════ 五、PDF / 统计 / 会员 ══════════════════════

@app.get("/api/pdf")
def pdf_list(category: Optional[str]=Query(None), page: int=Query(1,ge=1)):
    conn = _conn()
    cond, params = [], []
    if category: cond.append("pm.category=?"); params.append(category)
    where = " WHERE " + " AND ".join(cond) if cond else ""
    total = conn.execute(f"SELECT COUNT(*) FROM pdf_materials pm{where}", params).fetchone()[0]
    rows = conn.execute(f"""SELECT pm.id,pm.title,pm.description,pm.file_url,pm.category,
        COALESCE(mu.nickname,''),pm.created_at FROM pdf_materials pm
        LEFT JOIN math_users mu ON pm.uploader_id=mu.id{where}
        ORDER BY pm.created_at DESC LIMIT 20 OFFSET ?""", params + [(page-1)*20]).fetchall()
    return {"data":[{"id":r[0],"title":r[1],"description":r[2] or "","file_url":r[3],"category":r[4] or "","uploader_nickname":r[5],"created_at":r[6]} for r in rows],"total":total}


@app.get("/api/stats")
def stats():
    conn = _conn()
    return {"total_problems": conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0],
            "total_exam_problems": conn.execute("SELECT COUNT(*) FROM problems WHERE source LIKE '%考研%'").fetchone()[0],
            "total_books": 13, "total_pdfs": conn.execute("SELECT COUNT(*) FROM pdf_materials").fetchone()[0]}


@app.get("/api/membership/{user_id}")
def membership(user_id: str):
    conn = _conn()
    u = conn.execute("SELECT membership, membership_expires_at FROM math_users WHERE id=?", [user_id]).fetchone()
    if not u: raise HTTPException(404)
    expired = False
    if u[1]:
        try: expired = date.fromisoformat(str(u[1])[:10]) < date.today()
        except: pass
    return {"membership": u[0] if not expired else "free", "expires_at": u[1], "expired": expired}


# ══════════════════════ 六、导入题目 ══════════════════════

from pydantic import BaseModel as _BM

class _ImportProblem(_BM):
    title: str; content: str; subject: str; difficulty: int
    tags: list[str] = []; solution: str = ""

@app.post("/api/import-problem")
def import_problem(body: _ImportProblem):
    conn = _conn()
    if _IS_PG:
        cur = conn.execute(
            "INSERT INTO problems (title, content, subject, difficulty, tags, solution) VALUES (?,?,?,?,?,?) RETURNING id",
            [body.title, body.content, body.subject, body.difficulty, json.dumps(body.tags), body.solution])
        row = cur.fetchone()
        return {"ok": True, "id": row["id"] if row else None}
    else:
        conn.execute("INSERT INTO problems (title, content, subject, difficulty, tags, solution) VALUES (?,?,?,?,?,?)",
                     [body.title, body.content, body.subject, body.difficulty, json.dumps(body.tags), body.solution])
        conn.commit()
        return {"ok": True, "id": conn.execute("SELECT last_insert_rowid()").fetchone()[0]}


@app.post("/api/import-problems-batch")
def import_problems_batch(body: list[_ImportProblem]):
    conn = _conn()
    count = 0
    for p in body:
        if _IS_PG:
            conn.execute("INSERT INTO problems (title, content, subject, difficulty, tags, solution) VALUES (?,?,?,?,?,?)",
                         [p.title, p.content, p.subject, p.difficulty, json.dumps(p.tags), p.solution])
        else:
            conn.execute("INSERT INTO problems (title, content, subject, difficulty, tags, solution) VALUES (?,?,?,?,?,?)",
                         [p.title, p.content, p.subject, p.difficulty, json.dumps(p.tags), p.solution])
        count += 1
    conn.commit()
    return {"ok": True, "count": count}


# ══════════════════════ 七、训练计划（从 Hydro Training 抄） ══════════════════════

from pydantic import BaseModel as _BM2

class _PlanCreate(_BM2):
    title: str; description: str = ""; problem_ids: list[int]; subject: str = ""

@app.get("/api/plans")
def plans_list():
    conn = _conn()
    rows = conn.execute("""SELECT tp.id,tp.title,tp.description,tp.subject,
        (SELECT COUNT(*) FROM plan_problems WHERE plan_id=tp.id) as total,
        (SELECT COUNT(*) FROM plan_problems pp JOIN user_problem_status ups ON pp.problem_id=ups.problem_id
         WHERE pp.plan_id=tp.id AND ups.user_id=?) as done
        FROM training_plans tp ORDER BY tp.id""", [""]).fetchall()
    return [{"id":r[0],"title":r[1],"description":r[2],"subject":r[3],"total":r[4],"done":r[5]} for r in rows]

@app.get("/api/plans/{plan_id}")
def plan_get(plan_id: int):
    conn = _conn()
    row = conn.execute("SELECT * FROM training_plans WHERE id=?", [plan_id]).fetchone()
    if not row: raise HTTPException(404)
    problems = conn.execute("""SELECT p.*, ups.status, ups.wrong_reason FROM problems p
        JOIN plan_problems pp ON p.id=pp.problem_id
        LEFT JOIN user_problem_status ups ON p.id=ups.problem_id AND ups.user_id=?
        WHERE pp.plan_id=? ORDER BY pp.sort_order""", ["", plan_id]).fetchall()
    parsed = []
    for r in problems:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags","[]")) if isinstance(d.get("tags"), str) else (d.get("tags") or [])
        parsed.append(d)
    return {"plan":{"id":row[0],"title":row[1],"description":row[2],"subject":row[3]},
            "problems":parsed}

# ══════════════════════ 追加：训练计划 + 评级系统 + 评论区 ══════════════════════

from pydantic import BaseModel as _BM2

class _PlanCreate(_BM2):
    title: str; description: str = ""; problem_ids: list[int]; subject: str = ""

@app.get("/api/plans")
def plans_list():
    conn = _conn()
    rows = conn.execute("""SELECT tp.id,tp.title,tp.description,tp.subject,
        (SELECT COUNT(*) FROM plan_problems WHERE plan_id=tp.id) as total,
        (SELECT COUNT(*) FROM plan_problems pp JOIN user_problem_status ups ON pp.problem_id=ups.problem_id
         WHERE pp.plan_id=tp.id AND ups.user_id=?) as done
        FROM training_plans tp ORDER BY tp.id""", [""]).fetchall()
    return [{"id":r[0],"title":r[1],"description":r[2],"subject":r[3],"total":r[4],"done":r[5]} for r in rows]

@app.get("/api/plans/{plan_id}")
def plan_get(plan_id: int):
    conn = _conn()
    row = conn.execute("SELECT * FROM training_plans WHERE id=?", [plan_id]).fetchone()
    if not row: raise HTTPException(404)
    problems = conn.execute("""SELECT p.*, ups.status, ups.wrong_reason FROM problems p
        JOIN plan_problems pp ON p.id=pp.problem_id
        LEFT JOIN user_problem_status ups ON p.id=ups.problem_id AND ups.user_id=?
        WHERE pp.plan_id=? ORDER BY pp.sort_order""", ["", plan_id]).fetchall()
    parsed = []
    for r in problems:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags","[]")) if isinstance(d.get("tags"), str) else (d.get("tags") or [])
        parsed.append(d)
    return {"plan":{"id":row[0],"title":row[1],"description":row[2],"subject":row[3]},
            "problems":parsed}

# ══════════════════════ 评级系统（从 DMOJ 抄 ELO-MMR） ══════════════════════

RATING_INIT = 1000
EXP_PER_SOLVE = 10
EXP_PER_WRONG = 2

def _update_rating(user_id: str, status: str):
    conn = _conn()
    u = conn.execute("SELECT rating, exp, solved_count FROM math_users WHERE id=?", [user_id]).fetchone()
    if not u: return
    rating = u[0] or RATING_INIT
    exp = u[1] or 0
    solved = u[2] or 0
    if status == "correct":
        solved += 1
        exp += EXP_PER_SOLVE
        gain = max(1, min(5, 20 - (rating - RATING_INIT) // 100))
        rating += gain
    elif status == "wrong":
        exp += EXP_PER_WRONG
        rating = max(RATING_INIT - 200, rating - 1)
    conn.execute("UPDATE math_users SET rating=?, exp=?, solved_count=? WHERE id=?",
                 [rating, exp, solved, user_id])
    conn.commit()

@app.get("/api/leaderboard")
def leaderboard(page: int=Query(1,ge=1)):
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) FROM math_users").fetchone()[0]
    rows = conn.execute("""SELECT id, nickname, rating, exp, solved_count
        FROM math_users ORDER BY rating DESC, exp DESC LIMIT 50 OFFSET ?""", [(page-1)*50]).fetchall()
    return {"data":[{"id":r[0],"nickname":r[1] or r[0][:8],"rating":r[2],"exp":r[3],"solved":r[4]} for r in rows],
            "total":total}

@app.get("/api/user/{user_id}/profile")
def user_profile(user_id: str):
    conn = _conn()
    u = conn.execute("SELECT id, nickname, rating, exp, solved_count, created_at FROM math_users WHERE id=?", [user_id]).fetchone()
    if not u: raise HTTPException(404)
    return {"id":u[0],"nickname":u[1] or u[0][:8],"rating":u[2],"exp":u[3],"solved":u[4],"created_at":u[5]}

# ══════════════════════ 问题评论区 ══════════════════════

@app.get("/api/problems/{problem_id}/comments")
def problem_comments(problem_id: int):
    conn = _conn()
    rows = conn.execute("""SELECT pc.id, pc.content, COALESCE(mu.nickname, mu.id, '匿名'), pc.created_at
        FROM problem_comments pc LEFT JOIN math_users mu ON pc.user_id=mu.id
        WHERE pc.problem_id=? ORDER BY pc.created_at""", [problem_id]).fetchall()
    return [{"id":r[0],"content":r[1],"user_nickname":r[2],"created_at":r[3]} for r in rows]

@app.post("/api/problems/{problem_id}/comments")
def problem_comment_create(problem_id: int, body: dict):
    user_id = body.get("user_id")
    content = body.get("content","").strip()
    if not user_id or not content: raise HTTPException(400, "缺少 user_id 或 content")
    conn = _conn()
    conn.execute("INSERT INTO problem_comments (problem_id, user_id, content) VALUES (?,?,?)",
                 [problem_id, user_id, content])
    conn.commit()
    return {"ok": True}

# ══════════════════════ 编程题模板（预留 judge0 API 集成点） ══════════════════════

@app.post("/api/code-submit")
def code_submit(body: dict):
    """提交编程题答案。目前只存代码+语言，不入判题队列。
    后续接 judge0: POST /submissions?base64_encoded=false&wait=true"""
    problem_id = body.get("problem_id")
    user_id = body.get("user_id")
    code = body.get("code", "")
    language = body.get("language", "python")
    if not all([problem_id, user_id, code]): raise HTTPException(400, "缺少参数")
    conn = _conn()
    conn.execute("INSERT INTO code_submissions (problem_id, user_id, code, language, status) VALUES (?,?,?,?,'pending')",
                 [problem_id, user_id, code, language])
    conn.commit()
    return {"ok": True, "message": "代码已提交，待判题"}

@app.get("/api/code-submissions/{user_id}")
def code_submissions(user_id: str):
    conn = _conn()
    rows = conn.execute("""SELECT cs.id, cs.problem_id, cs.language, cs.status, cs.created_at,
        p.title FROM code_submissions cs JOIN problems p ON cs.problem_id=p.id
        WHERE cs.user_id=? ORDER BY cs.created_at DESC LIMIT 20""", [user_id]).fetchall()
    return [{"id":r[0],"problem_id":r[1],"language":r[2],"status":r[3],"created_at":r[4],"problem_title":r[5]} for r in rows]
