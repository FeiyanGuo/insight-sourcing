#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
digest.py —— 每周观点综述生成
- 取「最近 7 天」新增报告（没有 Key 时退化为按分类汇总的简易版）
- 调用 DeepSeek 产出结构化 Markdown 综述，写入 data/digests/<YYYY-Www>.md
"""
import os
import json
import datetime

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DIGESTS_DIR = os.path.join(DATA, "digests")
REPORTS_JSON = os.path.join(DATA, "reports.json")

with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

DIGEST_CFG = CONFIG["digest"]
MODEL = DIGEST_CFG["model"]
BASE_URL = DIGEST_CFG["base_url"]


def load_reports():
    if not os.path.exists(REPORTS_JSON):
        return []
    with open(REPORTS_JSON, encoding="utf-8") as f:
        return json.load(f)["reports"]


def recent_reports(days=7):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    rs = [r for r in load_reports() if parse_date(r["date"]) >= cutoff]
    rs.sort(key=lambda x: x["date"])
    return rs


def parse_date(s):
    return datetime.datetime.fromisoformat(s)


def week_key(d=None):
    d = d or datetime.datetime.now(datetime.timezone.utc)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def build_prompt(reports):
    start = reports[0]["date"][:10]
    end = reports[-1]["date"][:10]
    lines = []
    for r in reports:
        summary = (r.get("summary") or "").strip().replace("\n", " ")
        if len(summary) > 200:
            summary = summary[:200] + "…"
        lines.append(
            f"- 【{r['source']}】{r['title']}\n"
            f"  分类：{r['category']}｜日期：{r['date'][:10]}｜链接：{r['url']}\n"
            f"  摘要：{summary}"
        )
    listing = "\n".join(lines)
    sys_prompt = (
        "你是一位资深行业研究分析师，擅长把多家咨询/研究机构发布的报告，"
        "整理成清晰、可快速阅读的每周观点综述。请用简体中文输出 Markdown。"
    )
    user_prompt = f"""以下是本周（{start} ~ {end}）新增的 {len(reports)} 篇报告，来自多个机构。请整理成「每周咨询报告观点综述」：

要求：
1. 开头写一段「本周概览」（3-5 句话概括整体趋势与最值得关注的信号）。
2. 然后「按主题分组」列出关键观点；每条观点用 1-2 句话，并注明「来源机构 - 报告标题」并附上原文链接。
3. 最后给出「值得深读 TOP5」清单（按价值排序，含标题与链接）。
4. 不要编造报告里没有的内容；若某报告只有摘要，请基于摘要总结。

报告清单：
{listing}
"""
    return sys_prompt, user_prompt


def call_deepseek(sys_prompt, user_prompt):
    from openai import OpenAI
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    client = OpenAI(api_key=key, base_url=BASE_URL)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content


def fallback_digest(reports):
    """没有 AI Key 时的简易综述（按分类汇总）。"""
    by_cat = {}
    for r in reports:
        by_cat.setdefault(r["category"] or "未分类", []).append(r)
    out = ["# 每周咨询报告观点综述（简易版·未使用AI）\n"]
    out.append(f"> 本周共 {len(reports)} 篇报告，覆盖 {len(by_cat)} 个分类。\n")
    for cat, rs in by_cat.items():
        out.append(f"## {cat}（{len(rs)} 篇）\n")
        for r in rs:
            out.append(f"- [{r['title']}]({r['url']}) — {r['source']}（{r['date'][:10]}）")
            if r.get("summary"):
                out.append(f"  - 摘要：{r['summary'][:150]}")
        out.append("")
    out.append("> 提示：在仓库 Secrets 配置 DEEPSEEK_API_KEY 后，将自动生成由 AI 整理的观点综述。")
    return "\n".join(out)


def record_index(week, count):
    """把每期周报记录到 data/digests.json，供站点读取。"""
    idx_path = os.path.join(DATA, "digests.json")
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
    else:
        idx = []
    idx = [d for d in idx if d["week"] != week]
    idx.append({"week": week, "count": count, "generated": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    idx.sort(key=lambda x: x["week"], reverse=True)
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


def main():
    reports = recent_reports(days=7)
    if not reports:
        print("近 7 天没有新增报告，跳过周报生成。")
        return
    wk = week_key()
    os.makedirs(DIGESTS_DIR, exist_ok=True)
    out_path = os.path.join(DIGESTS_DIR, wk + ".md")

    content = call_deepseek(*build_prompt(reports))
    if content:
        # 加一个标题头
        header = f"# 每周咨询报告观点综述（{wk}）\n\n> 由 AI 基于 {len(reports)} 篇本周新增报告整理生成。\n\n"
        content = header + content
        tag = "AI"
    else:
        content = fallback_digest(reports)
        tag = "简易"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    record_index(wk, len(reports))
    print(f"已生成周报 [{tag}]：{out_path}（基于 {len(reports)} 篇报告）")


if __name__ == "__main__":
    main()
