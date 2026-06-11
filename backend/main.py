"""
jack门 — FastAPI 后端（Supabase 持久化版 + 匹配冷却）

API:
  POST /submit                    — 提交问卷
  GET  /match/{user_id}           — 获取匹配结果
  POST /match/{user_id}/connect   — 标记已连接
  POST /match/{user_id}/ignore    — 换一批（忽略此人）
  GET  /notifications/{user_id}   — 查看通知
  POST /notifications/{user_id}/read — 标记已读
  GET  /pool                      — 池子统计
  GET  /admin/stats               — 管理后台统计
  GET  /health                    — 健康检查
"""

import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from models import (
    QuizSubmit, MatchResponse, MatchItem, PoolInfo,
    Notification, NotificationList, ConnectionAction, AdminStats,
)
from match import match as run_match

# ---- 初始化 ----
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

app = FastAPI(title="jack门", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def _db():
    if supabase is None:
        raise HTTPException(status_code=500, detail="数据库未配置")
    return supabase


# ---- 路由 ----

@app.get("/health")
def health():
    status = "ok" if supabase else "no_db"
    return {"status": status}


@app.post("/submit")
def submit(data: QuizSubmit):
    db = _db()
    user_id = str(uuid.uuid4())[:8]

    db.table("users").insert({
        "id": user_id,
        "role": data.role,
        "answers": data.answers,
        "contact": data.contact,
    }).execute()

    freshmen = db.table("users").select("id", count="exact").eq("role", "freshman").execute().count
    seniors = db.table("users").select("id", count="exact").eq("role", "senior").execute().count

    return {
        "user_id": user_id,
        "message": f"已提交！当前池子有 {freshmen + seniors} 人（新生 {freshmen}，老生 {seniors}）",
    }


@app.get("/match/{user_id}")
def get_match(user_id: str):
    db = _db()

    user_res = db.table("users").select("*").eq("id", user_id).execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="用户不存在，先提交问卷")
    user = user_res.data[0]

    target_role = "senior" if user["role"] == "freshman" else "freshman"
    pool_res = db.table("users").select("*").eq("role", target_role).execute()

    # 获取用户已有的连接/忽略记录
    conn_res = db.table("connections").select("matched_id,status").eq("user_id", user_id).execute()
    handled_ids = {r["matched_id"] for r in conn_res.data if r["status"] in ("connected", "ignored")}

    pool = [
        {"id": p["id"], "answers": p["answers"], "contact": p["contact"]}
        for p in pool_res.data
        if p["id"] != user_id and p["id"] not in handled_ids
    ]

    if not pool:
        return MatchResponse(user_id=user_id, matches=[])

    matches = run_match(user["answers"], pool)
    match_items = [MatchItem(**m) for m in matches]

    # 双向通知
    my_label = "新生" if user["role"] == "freshman" else "老生"
    for m in matches:
        db.table("notifications").insert({
            "user_id": m["matched_id"],
            "from_id": user_id,
            "from_contact": user["contact"],
            "from_role": my_label,
            "message": f"一位{my_label}匹配到了你！",
            "read": False,
        }).execute()

    return MatchResponse(user_id=user_id, matches=match_items)


@app.post("/match/{user_id}/connect")
def connect_match(user_id: str, body: ConnectionAction):
    db = _db()

    # 查是否已存在记录
    existing = db.table("connections").select("*").eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    if existing.data:
        db.table("connections").update({"status": "connected"}).eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    else:
        db.table("connections").insert({
            "user_id": user_id,
            "matched_id": body.matched_id,
            "status": "connected",
        }).execute()

    return {"status": "ok", "message": "已连接"}


@app.post("/match/{user_id}/ignore")
def ignore_match(user_id: str, body: ConnectionAction):
    db = _db()

    existing = db.table("connections").select("*").eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    if existing.data:
        db.table("connections").update({"status": "ignored"}).eq("user_id", user_id).eq("matched_id", body.matched_id).execute()
    else:
        db.table("connections").insert({
            "user_id": user_id,
            "matched_id": body.matched_id,
            "status": "ignored",
        }).execute()

    return {"status": "ok", "message": "已忽略，换一批"}


@app.get("/notifications/{user_id}")
def get_notifications(user_id: str):
    db = _db()

    user_res = db.table("users").select("id").eq("id", user_id).execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="用户不存在")

    notif_res = db.table("notifications").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    notifs = notif_res.data
    unread = sum(1 for n in notifs if not n["read"])

    return NotificationList(
        user_id=user_id,
        unread=unread,
        notifications=[Notification(
            from_id=n["from_id"],
            from_contact=n.get("from_contact", ""),
            from_role=n.get("from_role", ""),
            message=n["message"],
            read=n["read"],
            time=n.get("created_at", ""),
        ) for n in notifs],
    )


@app.post("/notifications/{user_id}/read")
def mark_read(user_id: str):
    db = _db()
    db.table("notifications").update({"read": True}).eq("user_id", user_id).eq("read", False).execute()
    return {"status": "ok"}


@app.get("/pool")
def get_pool():
    db = _db()
    freshmen = db.table("users").select("id", count="exact").eq("role", "freshman").execute().count
    seniors = db.table("users").select("id", count="exact").eq("role", "senior").execute().count
    return PoolInfo(total=freshmen + seniors, freshmen=freshmen, seniors=seniors)


@app.get("/admin/stats")
def admin_stats():
    db = _db()
    users = db.table("users").select("id", count="exact").execute().count
    freshmen = db.table("users").select("id", count="exact").eq("role", "freshman").execute().count
    seniors = db.table("users").select("id", count="exact").eq("role", "senior").execute().count
    connections = db.table("connections").select("id", count="exact").eq("status", "connected").execute().count
    ignored = db.table("connections").select("id", count="exact").eq("status", "ignored").execute().count
    notifs = db.table("notifications").select("id", count="exact").execute().count

    return AdminStats(
        total_users=users,
        freshmen=freshmen,
        seniors=seniors,
        total_matches=notifs,
        total_connections=connections,
        total_ignored=ignored,
    )
