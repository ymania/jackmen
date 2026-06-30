"""
Pydantic 数据模型 — jack门 + 做题平台 统一
"""
from typing import Literal, Optional, List
from pydantic import BaseModel


# ═══════════════════════════════════════════
# 匹配系统 (jack门)
# ═══════════════════════════════════════════

class QuizSubmit(BaseModel):
    role: Literal["freshman", "senior"]
    answers: list[int]
    contact: str


class MatchItem(BaseModel):
    matched_id: str
    score: float
    reason: str
    contact: str


class MatchResponse(BaseModel):
    user_id: str
    matches: list[MatchItem]


class PoolInfo(BaseModel):
    total: int
    freshmen: int
    seniors: int


class Notification(BaseModel):
    from_id: str
    from_contact: str
    from_role: str
    message: str
    read: bool = False
    time: str = ""


class NotificationList(BaseModel):
    user_id: str
    unread: int
    notifications: list[Notification] = []


class ConnectionAction(BaseModel):
    matched_id: str


class AdminStats(BaseModel):
    total_users: int
    freshmen: int
    seniors: int
    total_matches: int
    total_connections: int
    total_ignored: int


# ═══════════════════════════════════════════
# 用户系统（做题平台）
# ═══════════════════════════════════════════

class UserRegister(BaseModel):
    email: str
    password: str
    nickname: str = ""


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    nickname: str
    membership: str
    membership_expires_at: Optional[str] = None
    created_at: Optional[str] = None


# ═══════════════════════════════════════════
# 题库
# ═══════════════════════════════════════════

class ProblemOut(BaseModel):
    id: int
    title: str
    content: str
    subject: str
    difficulty: int
    tags: List[str] = []
    solution: str = ""
    source: str = ""
    created_at: Optional[str] = None


class AnswerSubmit(BaseModel):
    user_id: str
    problem_id: int
    status: str  # correct / wrong
    wrong_reason: str = ""


class WrongProblemOut(BaseModel):
    id: int
    problem_id: int
    title: str
    subject: str
    difficulty: int
    status: str
    wrong_reason: str
    marked: bool
    attempted_at: Optional[str] = None


# ═══════════════════════════════════════════
# 论坛
# ═══════════════════════════════════════════

class ForumCategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    post_count: int = 0


class ForumPostCreate(BaseModel):
    category_id: int
    user_id: str
    title: str
    content: str


class ForumPostOut(BaseModel):
    id: int
    category_id: int
    category_name: str = ""
    user_id: Optional[str] = None
    user_nickname: str = ""
    title: str
    content: str
    comment_count: int = 0
    created_at: Optional[str] = None


class ForumCommentCreate(BaseModel):
    post_id: int
    user_id: str
    content: str


class ForumCommentOut(BaseModel):
    id: int
    post_id: int
    user_id: Optional[str] = None
    user_nickname: str = ""
    content: str
    created_at: Optional[str] = None


# ═══════════════════════════════════════════
# PDF 资料
# ═══════════════════════════════════════════

class PdfMaterialOut(BaseModel):
    id: int
    title: str
    description: str
    file_url: str
    category: str
    uploader_nickname: str = ""
    created_at: Optional[str] = None


# ═══════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════

class StatsOut(BaseModel):
    total_problems: int = 0
    total_exam_problems: int = 0
    total_books: int = 0
    total_pdfs: int = 0
