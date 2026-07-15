#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch.py —— 报告抓取器
- 支持两种来源类型：
    rss : 直接给 RSS 源地址（麦肯锡 / Gartner / 公众号转RSS 等）
    web : 给网站首页，由程序自动找文章链接再逐篇提取正文（甲子光年官网等）
- 输出：data/reports.json（索引，去重）+ data/reports/<id>.md（每篇报告）
- 微信来源(via=wechat_rss)：优先用 RSS 摘要；若抓不到正文则只存图/链接提示。
"""
import os
import re
import json
import time
import hashlib
import datetime
from urllib.parse import urljoin

import yaml
import feedparser
import httpx
from bs4 import BeautifulSoup
import trafilatura

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REPORTS_DIR = os.path.join(DATA, "reports")
REPORTS_JSON = os.path.join(DATA, "reports.json")

with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

UA = CONFIG["fetch"]["user_agent"]
DELAY = CONFIG["fetch"]["delay_seconds"]
TIMEOUT = CONFIG["fetch"]["timeout"]
MAX_RETRIES = CONFIG["fetch"]["max_retries"]
MAX_WEB = CONFIG["fetch"].get("max_articles_per_web", 8)
MAX_RSS_FULL = CONFIG["fetch"].get("max_articles_per_rss_fulltext", 10)
# 全文抓取用更短超时、只重试 1 次：抓不到就回退 RSS/网页摘要，绝不长时间阻塞
FULLTEXT_TIMEOUT = CONFIG["fetch"].get("fulltext_timeout", 10)
FULLTEXT_RETRIES = 1


# ------------------------- 工具 -------------------------
def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def normalize_url(u):
    u = (u or "").strip().split("#")[0]
    return u


def url_hash(u):
    return hashlib.sha1(u.encode("utf-8")).hexdigest()[:12]


def load_sources():
    with open(os.path.join(ROOT, "sources.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def http_get(url, timeout=TIMEOUT, retries=MAX_RETRIES):
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    for attempt in range(retries):
        try:
            r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404, 401, 429):
                # 明确拒绝/不存在，无需重试
                print(f"    ! HTTP {r.status_code}（跳过）{url}")
                return None
        except Exception as e:
            print(f"    ! 请求失败 {url}: {e}")
        if attempt < retries - 1:
            time.sleep(DELAY)
    return None


def strip_tags(html):
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def extract_text(url, html):
    """尽量提取正文全文；失败回退到 <p> 拼接。"""
    try:
        text = trafilatura.extract(html, url=url)
        if text and len(text.strip()) > 200:
            return text.strip()
    except Exception:
        pass
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        t.decompose()
    paras = [p.get_text(strip=True) for p in soup.find_all("p")]
    text = "\n".join([p for p in paras if p])
    return text.strip()


def extract_date(html):
    """从网页 meta 中尽量提取发布时间。"""
    soup = BeautifulSoup(html or "", "html.parser")
    for prop in ("article:published_time", "datePublished", "pubdate", "publishdate"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            try:
                return datetime.datetime.fromisoformat(tag["content"].replace("Z", "+00:00"))
            except Exception:
                pass
    # 常见中文格式：2026-04-21 / 2026年04月21日
    m = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})", html or "")
    if m:
        try:
            return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                     tzinfo=datetime.timezone.utc)
        except Exception:
            pass
    return now_utc()


# ------------------------- 单篇报告构建 -------------------------
def make_report(source, title, link, date, summary, has_full_text):
    url = normalize_url(link)
    rid = url_hash(url)
    return {
        "id": rid,
        "title": title.strip(),
        "url": url,
        "source": source.get("name", ""),
        "category": source.get("category", ""),
        "via": source.get("via", ""),
        "date": date.isoformat(),
        "summary": (summary or "").strip(),
        "has_full_text": bool(has_full_text),
    }


# ------------------------- RSS 抓取 -------------------------
def fetch_rss(source):
    new_count = 0
    d = feedparser.parse(source["url"])
    if d.bozo and not d.entries:
        # feedparser 自带抓取失败，尝试用 httpx 拉取后解析
        r = http_get(source["url"])
        if not r:
            print("    ! RSS 无法获取")
            return 0
        d = feedparser.parse(r.text)
    processed = 0
    total = 0
    for entry in d.entries:
        title = (entry.get("title") or "").strip()
        link = entry.get("link") or ""
        if not title or not link:
            continue
        total += 1
        summary = strip_tags(entry.get("summary") or entry.get("description") or "")
        date = now_utc()
        if entry.get("published_parsed"):
            date = datetime.datetime(*entry["published_parsed"][:6], tzinfo=datetime.timezone.utc)
        elif entry.get("updated_parsed"):
            date = datetime.datetime(*entry["updated_parsed"][:6], tzinfo=datetime.timezone.utc)

        full_text = ""
        # 尽量抓全文（短超时、只重试 1 次；公众号/付费页抓不到就回退摘要）
        if processed < MAX_RSS_FULL:
            rr = http_get(link, timeout=FULLTEXT_TIMEOUT, retries=FULLTEXT_RETRIES)
            if rr:
                full_text = extract_text(link, rr.text)
            processed += 1
            time.sleep(DELAY)
        rep = make_report(source, title, link, date, summary, bool(full_text))
        if save_report(rep, full_text):
            new_count += 1
            print(f"    + [{rep['source']}] {title[:40]}（{'全文' if full_text else '摘要'}）")
    print(f"    -> RSS 共 {total} 条，本次新增写入 {new_count} 篇")
    return new_count


# ------------------------- Web 抓取（如甲子光年官网）-------------------------
def fetch_web(source):
    new_count = 0
    r = http_get(source["url"])
    if not r:
        return 0
    soup = BeautifulSoup(r.text, "html.parser")
    selectors = source.get("list_selectors", [])
    links = set()
    for sel in selectors:
        for a in soup.select(sel):
            href = a.get("href")
            if href:
                links.add(href)
    # 兜底：抓取所有看起来像文章的链接
    if not links:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"article|report|post|news|detail", href, re.I):
                links.add(href)

    abs_links = []
    for l in links:
        if l.startswith("http"):
            abs_links.append(l)
        else:
            abs_links.append(urljoin(source["url"], l))

    seen = set()
    total = 0
    for link in abs_links:
        link = normalize_url(link)
        if link in seen:
            continue
        seen.add(link)
        if total >= MAX_WEB:
            break
        total += 1
        rr = http_get(link, timeout=FULLTEXT_TIMEOUT, retries=FULLTEXT_RETRIES)
        if not rr:
            continue
        title_tag = BeautifulSoup(rr.text, "html.parser").title
        title = strip_tags(str(title_tag)) if title_tag else link
        date = extract_date(rr.text)
        full_text = extract_text(link, rr.text)
        summary = full_text[:300] if full_text else ""
        rep = make_report(source, title, link, date, summary, bool(full_text))
        if save_report(rep, full_text):
            new_count += 1
            print(f"    + [{rep['source']}] {title[:40]}（{'全文' if full_text else '摘要'}）")
        time.sleep(DELAY)
    print(f"    -> Web 共抓 {total} 个链接，本次新增写入 {new_count} 篇")
    return new_count


# ------------------------- 落盘 / 去重 -------------------------
def load_index():
    if os.path.exists(REPORTS_JSON):
        with open(REPORTS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {"reports": []}


def format_markdown(report, full_text):
    return f"""---
title: {json.dumps(report['title'], ensure_ascii=False)}
source: {report['source']}
category: {report['category']}
date: {report['date']}
url: {report['url']}
via: {report['via']}
has_full_text: {report['has_full_text']}
---

# {report['title']}

- 来源：{report['source']}
- 分类：{report['category']}
- 发布：{report['date']}
- 原文：{report['url']}

## 摘要

{report['summary']}

## 正文

{full_text if full_text else '（该来源仅提供摘要/需注册，未抓取全文；请点击上方原文链接查看完整内容）'}
"""


def save_report(report, full_text):
    idx = load_index()
    existing = {r["id"] for r in idx["reports"]}
    if report["id"] in existing:
        return False
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, report["id"] + ".md"), "w", encoding="utf-8") as f:
        f.write(format_markdown(report, full_text))
    idx["reports"].append(report)
    idx["reports"].sort(key=lambda x: x["date"], reverse=True)
    with open(REPORTS_JSON, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    return True


# ------------------------- 主流程 -------------------------
def main():
    sources = load_sources()
    total_new = 0
    for s in sources:
        if not s.get("enabled", True):
            continue
        if str(s.get("url", "")).startswith("REPLACE_WITH"):
            print(f"[跳过] {s['name']}：尚未配置 RSS 地址（见 README）")
            continue
        print(f"[抓取] {s['name']} ({s['type']})")
        try:
            if s["type"] == "rss":
                total_new += fetch_rss(s)
            elif s["type"] == "web":
                total_new += fetch_web(s)
            else:
                print(f"    ! 未知类型 {s['type']}")
                continue
        except Exception as e:
            print(f"    ! {s['name']} 出错: {e}")
            continue
    print(f"\n完成：本次新增 {total_new} 篇报告。")


if __name__ == "__main__":
    main()
