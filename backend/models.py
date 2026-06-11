"""
Pydantic 数据模型
"""
from typing import Literal, Optional
from pydantic import BaseModel


class QuizSubmit(BaseModel):
    """提交问卷的请求体"""
    role: Literal["freshman", "senior"]
    answers: list[int]   # 12 个答案，每项 0-3
    contact: str         # 微信号/QQ，匹配后展示给对方


class MatchItem(BaseModel):
    """单条匹配结果"""
    matched_id: str      # 被匹配用户的 ID（用于 connect/ignore）
    score: float
    reason: str
    contact: str


class MatchResponse(BaseModel):
    """匹配结果响应"""
    user_id: str
    matches: list[MatchItem]


class PoolInfo(BaseModel):
    """当前池子信息"""
    total: int
    freshmen: int
    seniors: int


class Notification(BaseModel):
    """单条通知"""
    from_id: str
    from_contact: str
    from_role: str
    message: str
    read: bool = False
    time: str = ""


class NotificationList(BaseModel):
    """通知列表响应"""
    user_id: str
    unread: int
    notifications: list[Notification] = []


class ConnectionAction(BaseModel):
    """连接操作"""
    matched_id: str


class AdminStats(BaseModel):
    """管理后台统计"""
    total_users: int
    freshmen: int
    seniors: int
    total_matches: int
    total_connections: int
    total_ignored: int
