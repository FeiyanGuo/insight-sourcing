#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py —— 由 data/ 生成静态站点到 docs/
页面：首页 / 全部报告 / 报告详情 / 每周综述列表 / 周报详情
"""
import os
import json
import datetime

import yaml
import markdown
from jinja2 import Environment, FileSystemLoader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REPORTS_DIR = os.path.join(DATA, "reports")
DIGESTS_DIR = os.path.join(DATA, "digests")
SITE = os.path.join(ROOT, "docs")
TEMPLATES = os.path.join(ROOT, "templates")

with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)
SITE_CFG = CONFIG["site"]


def load_reports():
    p = os.path.join(DATA, "reports.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)["reports"]


def load_digest_index():
    p = os.path.join(DATA, "digests.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def read_md_body(path):
    text = open(path, encoding="utf-8").read()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.strip()


def md_to_html(md):
    return markdown.markdown(md, extensions=["extra", "fenced_code", "tables"])


def first_heading(md):
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def main():
    os.makedirs(os.path.join(SITE, "reports"), exist_ok=True)
    os.makedirs(os.path.join(SITE, "digests"), exist_ok=True)

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False)
    site = {
        "title": SITE_CFG.get("title", "洞察报告 Sourcing"),
        "subtitle": SITE_CFG.get("subtitle", ""),
    }
    updated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    reports = load_reports()
    digest_idx = load_digest_index()

    sources = sorted({r["source"] for r in reports})
    categories = sorted({r["category"] for r in reports if r.get("category")})

    latest_digest = digest_idx[0] if digest_idx else None

    # 首页
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("home.html").render(
            site=site, reports=reports, latest_digest=latest_digest, updated=updated))

    # 全部报告
    with open(os.path.join(SITE, "reports.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("reports.html").render(
            site=site, reports=reports, sources=sources, categories=categories, updated=updated))

    # 报告详情
    for r in reports:
        md_path = os.path.join(REPORTS_DIR, r["id"] + ".md")
        if not os.path.exists(md_path):
            continue
        body = read_md_body(md_path)
        with open(os.path.join(SITE, "reports", r["id"] + ".html"), "w", encoding="utf-8") as f:
            f.write(env.get_template("report_detail.html").render(
                site=site, r=r, content=md_to_html(body), updated=updated))

    # 周报列表
    with open(os.path.join(SITE, "digests.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("digests.html").render(
            site=site, digests=digest_idx, updated=updated))

    # 周报详情
    for d in digest_idx:
        md_path = os.path.join(DIGESTS_DIR, d["week"] + ".md")
        if not os.path.exists(md_path):
            continue
        body = read_md_body(md_path)
        html = md_to_html(body)
        # 用第一行为标题覆盖
        with open(os.path.join(SITE, "digests", d["week"] + ".html"), "w", encoding="utf-8") as f:
            f.write(env.get_template("digest_detail.html").render(
                site=site, week=d["week"], content=html, updated=updated))

    # 禁止 GitHub Pages 的 Jekyll 处理我们的静态文件（避免误改 HTML）
    with open(os.path.join(SITE, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")

    print(f"站点已生成：{SITE}")
    print(f"  报告页 {len(reports)} 篇，周报 {len(digest_idx)} 期")


if __name__ == "__main__":
    main()
