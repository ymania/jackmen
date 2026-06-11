"""
匹配算法核心

输入：12 维答案向量（每题 0-3）
输出：与池子中其他人的匹配得分 + 理由
"""

# MBTI 维度映射：每个维度占 2 题（题号 0-7）
MBTI_DIMS = {
    "EI": [0, 1],  # 0=E倾向, 3=I倾向
    "SN": [2, 3],  # 0=S倾向, 3=N倾向
    "TF": [4, 5],  # 0=T倾向, 3=F倾向
    "JP": [6, 7],  # 0=J倾向, 3=P倾向
}

# 互助行为维度（题号 8-11）
HELP_DIMS = {
    "skill_area": 8,    # 擅长帮助的领域
    "help_style": 9,    # 求助习惯
    "collab_style": 10, # 协作偏好 (0-1=带节奏, 2-3=跟节奏)
    "help_prefer": 11,  # 愿意帮什么样的人
}

# 第 9 题选项含义
AREA_LABELS = ["学习方法", "技术工具", "人际关系", "生活信息"]


def _mbti_score(answers: list[int], dim: str) -> float:
    """计算 MBTI 某一维度的倾向分数 (-1 到 1)"""
    q1, q2 = MBTI_DIMS[dim]
    # 每题答案 0-3，取平均映射到 -1 ~ 1
    avg = (answers[q1] + answers[q2]) / 2.0
    return (avg / 1.5) - 1  # 映射到 [-1, 1]


def _complement_score(user: list[int], other: list[int]) -> float:
    """
    互补分（0~1）：
    - skill_area 匹配：用户的求助习惯方向 == 对方的擅长领域
    - collab_style 互补：带节奏（0-1）配跟节奏（2-3）
    """
    score = 0.0

    # 技能互补：用户求助方向 == 对方擅长领域
    if user[HELP_DIMS["help_style"]] == other[HELP_DIMS["skill_area"]]:
        score += 0.6

    # 协作互补：带节奏 vs 跟节奏
    u_collab = user[HELP_DIMS["collab_style"]]
    o_collab = other[HELP_DIMS["collab_style"]]
    if (u_collab <= 1 and o_collab >= 2) or (u_collab >= 2 and o_collab <= 1):
        score += 0.4

    return min(score, 1.0)


def _similarity_score(user: list[int], other: list[int]) -> float:
    """
    相似分（0~1）：
    - MBTI 四维中同向的数量 / 4
    """
    same = 0
    for dim in ["EI", "SN", "TF", "JP"]:
        u_val = _mbti_score(user, dim)
        o_val = _mbti_score(other, dim)
        # 同号 = 同向
        if (u_val > 0 and o_val > 0) or (u_val < 0 and o_val < 0) or (abs(u_val) < 0.2 and abs(o_val) < 0.2):
            same += 1
    return same / 4.0


def _make_reason(user: list[int], other: list[int]) -> str:
    """生成匹配理由（模板化）"""
    parts = []

    # 性格相似点
    for dim, label in [("SN", "直觉型"), ("SN_inv", "感觉型"), ("TF", "思考型"), ("TF_inv", "情感型")]:
        pass  # 简化版：只报告互助互补

    # 互补点
    user_need = user[HELP_DIMS["help_style"]]
    other_skill = other[HELP_DIMS["skill_area"]]

    if user_need < 4 and other_skill < 4:
        parts.append(f"对方擅长{AREA_LABELS[other_skill]}，正好能帮到你。")

    # 协作互补
    u_collab = user[HELP_DIMS["collab_style"]]
    o_collab = other[HELP_DIMS["collab_style"]]
    if u_collab <= 1 and o_collab >= 2:
        parts.append("你习惯带节奏，对方习惯跟节奏，协作会很顺畅。")
    elif u_collab >= 2 and o_collab <= 1:
        parts.append("对方习惯带节奏，你习惯跟节奏，协作会很顺畅。")

    # 兜底
    if not parts:
        # 基于 MBTI 给一个通用理由
        for dim, pos_label, neg_label in [
            ("EI", "都喜欢社交场合", "都偏好安静的交流"),
            ("SN", "思考方式相近", "沟通风格互补"),
        ]:
            u_val = _mbti_score(user, dim)
            o_val = _mbti_score(other, dim)
            if (u_val > 0 and o_val > 0):
                parts.append(pos_label + "。")
                break
            elif (u_val < 0 and o_val < 0):
                parts.append(neg_label + "。")
                break

    if not parts:
        parts.append("你们的性格画像有一定契合度。")

    return " ".join(parts)


def match(user_answers: list[int], pool: list[dict]) -> list[dict]:
    """
    匹配主函数

    参数:
        user_answers: 12 个答案
        pool: 池子中其他人的数据 [{"id": ..., "answers": [...], "contact": ...}, ...]

    返回:
        按得分降序排列的匹配列表（含理由和联系方式）
    """
    results = []
    for other in pool:
        complement = _complement_score(user_answers, other["answers"])
        similarity = _similarity_score(user_answers, other["answers"])
        total = complement * 0.6 + similarity * 0.4
        reason = _make_reason(user_answers, other["answers"])

        results.append({
            "matched_id": other["id"],
            "score": round(total, 3),
            "reason": reason,
            "contact": other["contact"],
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:3]
