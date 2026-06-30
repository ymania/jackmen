#!/usr/bin/env python3
"""
题目 OCR 导入工具
用法: python3 ocr_import.py photo1.jpg photo2.png ... [--dry-run] [--auto-import]

第一性原理：
    照片 → OCR 文本 → 启发式解析（标题/内容/解析）→ JSON → POST 后端
    每张照片是独立的信息单元，互不依赖，天然可并行。
"""
import sys, json, os, re, argparse
import requests

# ══════════════════════ 配置 ══════════════════════
API_BASE = "http://localhost:8000"
IMPORT_URL = f"{API_BASE}/api/import-problem"
BATCH_URL = f"{API_BASE}/api/import-problems-batch"


def init_ocr():
    """懒加载 easyocr（首次调用才下载模型，~200MB）"""
    import easyocr
    return easyocr.Reader(['ch_sim', 'en'], gpu=False)


def ocr_image(reader, path: str) -> str:
    """OCR 一张图片，返回纯文本（按 y 坐标排序，从上到下）"""
    results = reader.readtext(path)
    if not results:
        return ""
    # 按 y 坐标排序（从上到下），同一行按 x 排序
    results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))
    lines = []
    prev_y = None
    for bbox, text, conf in results:
        y = bbox[0][1]
        if prev_y is not None and abs(y - prev_y) > 15:  # 新行
            lines.append(text)
        elif lines:
            lines[-1] += " " + text  # 同行拼接
        else:
            lines.append(text)
        prev_y = y
    return "\n".join(lines)


def parse_problem(raw_text: str) -> dict | None:
    """
    从 OCR 原始文本中解析题目结构。
    启发式规则：
      - 第一行/第一段 = 标题
      - 中间主体 = 题目内容
      - 以"解"/"答"/"解析"/"证明"/"Solution"开头的行之后 = 解析
    """
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if len(lines) < 2:
        return None

    title = lines[0]
    content_lines = []
    solution_lines = []
    in_solution = False

    solution_markers = ["解", "答", "解析", "证明", "Solution", "【解】", "【解析】", "【答案】"]

    for line in lines[1:]:
        if not in_solution and any(line.startswith(m) for m in solution_markers):
            in_solution = True
            # 去掉标记前缀
            for m in solution_markers:
                if line.startswith(m):
                    rest = line[len(m):].strip().lstrip("：:").strip()
                    if rest:
                        solution_lines.append(rest)
                    break
            continue
        if in_solution:
            solution_lines.append(line)
        else:
            content_lines.append(line)

    # 如果没有识别出解析段，最后一段可能是答案
    if not solution_lines and len(content_lines) > 3:
        # 取最后一段作为潜在解析
        pass

    return {
        "title": title,
        "content": "\n".join(content_lines),
        "solution": "\n".join(solution_lines),
        "subject": "",       # 需要用户补充
        "difficulty": 1,     # 默认
        "tags": [],
    }


def guess_subject(text: str) -> str:
    """根据关键词猜测科目"""
    keywords = {
        "数学分析": ["极限", "连续", "导数", "积分", "级数", "微分", "收敛", "lim", "∫", "dx", "∑"],
        "高等代数": ["矩阵", "行列式", "特征值", "向量", "线性", "多项式", "det", "rank"],
        "概率论与数理统计": ["概率", "期望", "方差", "正态分布", "随机", "样本", "P(", "N("],
        "常微分方程": ["微分方程", "dy/dx", "通解", "特解"],
    }
    text_lower = text.lower()
    for subject, kws in keywords.items():
        if any(kw.lower() in text_lower for kw in kws):
            return subject
    return ""


def process_single(reader, path: str) -> dict | None:
    """处理单张图片"""
    print(f"  OCR: {os.path.basename(path)} ...", end=" ", flush=True)
    raw = ocr_image(reader, path)
    if not raw:
        print("无文字")
        return None
    prob = parse_problem(raw)
    if not prob:
        print(f"解析失败（{len(raw)} 字符）")
        return None
    if not prob["subject"]:
        prob["subject"] = guess_subject(raw)
    if not prob["difficulty"] or prob["difficulty"] < 1:
        prob["difficulty"] = 1
    print(f"✓ [{prob['subject'] or '?'}] {prob['title'][:30]}")
    return prob


def import_batch(problems: list[dict]) -> bool:
    """批量导入后端"""
    if not problems:
        print("没有可导入的题目")
        return False
    try:
        resp = requests.post(BATCH_URL, json=problems, timeout=30)
        data = resp.json()
        if resp.ok and data.get("ok"):
            print(f"✅ 成功导入 {data['count']} 道题")
            return True
        else:
            print(f"❌ 导入失败: {data.get('detail', resp.text)}")
            return False
    except requests.ConnectionError:
        print(f"❌ 后端未启动 ({API_BASE})")
        return False


def main():
    parser = argparse.ArgumentParser(description="题目 OCR 导入工具")
    parser.add_argument("images", nargs="+", help="图片文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只 OCR 不导入，输出 JSON")
    parser.add_argument("--auto-import", action="store_true", help="OCR 后自动导入到后端")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")
    args = parser.parse_args()

    # 初始化 OCR（首次会下载模型）
    print("加载 OCR 模型...")
    reader = init_ocr()

    problems = []
    for path in args.images:
        if not os.path.exists(path):
            print(f"  跳过: {path} (文件不存在)")
            continue
        prob = process_single(reader, path)
        if prob:
            problems.append(prob)

    if not problems:
        print("\n没有成功解析的题目")
        return

    output = json.dumps(problems, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n📄 已保存: {args.output}")

    if args.dry_run or (not args.auto_import and not args.output):
        print(f"\n{'─'*40}")
        print(f"共 {len(problems)} 道题（预览）：")
        print(output[:2000])
        if len(output) > 2000:
            print(f"\n... ({len(output)} 字符，用 --output 保存完整输出)")
        print(f"\n使用 --auto-import 直接导入，或 --output result.json 保存")

    if args.auto_import:
        import_batch(problems)


if __name__ == "__main__":
    main()
