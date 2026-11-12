#!/usr/bin/env python3
"""Weekly digest: pull a few high-quality security/programming posts and
record what is worth learning from them.

Sources are plain public RSS/Atom feeds, requested once per feed with a short
timeout. A feed that refuses or times out is recorded and skipped - the job does
not retry aggressively and never tries to circumvent a block.

Inputs (env):
  MAX_PER_FEED  items kept per feed, default 3
  MAX_TOTAL     hard cap on collected items, default 15

Outputs:
  digest/<date>.md                      the digest article
  docs/self-review/<date>.md            machine-screened learning candidates
"""

import datetime as dt
import email.utils
import html
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIGEST_DIR = os.path.join(ROOT, "digest")
REVIEW_DIR = os.path.join(ROOT, "docs", "self-review")

FEEDS = [
    ("GitHub Blog", "https://github.blog/feed/"),
    ("Trail of Bits", "https://blog.trailofbits.com/feed/"),
    ("Project Zero", "https://googleprojectzero.blogspot.com/feeds/posts/default?alt=rss"),
    ("Help Net Security", "https://www.helpnetsecurity.com/feed/"),
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("Rust Blog", "https://blog.rust-lang.org/feed.xml"),
]

LEARN_RULES = [
    ("CI/供应链", ("github actions", "workflow", "ci/", "supply chain", "dependency",
                  "sbom", "artifact", "release", "build pipeline")),
    ("密钥与凭据", ("secret", "credential", "token", "leak", "hardening", "scan")),
    ("代码健壮性", ("fuzzing", "memory safety", "sandbox", "race", "unsafe", "hardening")),
    ("工具链/效率", ("rust", "tooling", "cli", "performance", "benchmark", "profiling")),
]

UA = "blog-digest/1.0"


def fetch(feed_url, timeout=15):
    req = urllib.request.Request(feed_url, headers={
        "User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise urllib.error.HTTPError(feed_url, resp.status, "unexpected status", None, None)
        return resp.read()


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean(text, limit=240):
    if not text:
        return ""
    text = TAG_RE.sub(" ", html.unescape(text))
    text = SPACE_RE.sub(" ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def parse(raw):
    """Return list of (title, link, summary, published) from RSS 2.0 or Atom."""
    root = ET.fromstring(raw)
    items = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = link = summary = published = ""
        for child in node:
            name = child.tag.split("}")[-1]
            if name == "title":
                title = clean(child.text or "", 200)
            elif name == "link":
                link = (child.text or "").strip() or child.attrib.get("href", "").strip()
            elif name in ("description", "summary", "content"):
                if not summary:
                    summary = clean(child.text or "")
            elif name in ("pubDate", "updated", "published") and not published:
                published = (child.text or "").strip()
        if title and link:
            items.append((title, link, summary, published))
    return items


def norm_date(value, fallback):
    if not value:
        return fallback
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.date().isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return value[:10]
    except Exception:
        return fallback


def screen(items):
    candidates = []
    for it in items:
        blob = (it["title"] + " " + it["summary"]).lower()
        for label, words in LEARN_RULES:
            if any(w in blob for w in words):
                candidates.append((label, it["title"], it["link"]))
                break
    return candidates


def main():
    per_feed = int(os.environ.get("MAX_PER_FEED", "3"))
    max_total = int(os.environ.get("MAX_TOTAL", "15"))
    today = dt.date.today().isoformat()
    collected, failed = [], []

    for name, url in FEEDS:
        if len(collected) >= max_total:
            break
        try:
            raw = fetch(url)
            parsed = parse(raw)
        except Exception as exc:  # noqa: BLE001 - a dead feed must not kill the job
            failed.append((name, url, "%s: %s" % (type(exc).__name__, exc)))
            print("SKIP %s (%s)" % (name, exc), file=sys.stderr)
            continue
        picked = parsed[:per_feed]
        if not picked:
            failed.append((name, url, "feed parsed but contained no usable item"))
            continue
        for title, link, summary, published in picked:
            if len(collected) >= max_total:
                break
            collected.append({
                "source": name, "title": title, "link": link,
                "summary": summary, "date": norm_date(published, today),
            })
        print("OK %s items=%d" % (name, len(picked)))

    if not collected:
        print("RESULT=NO_CONTENT every feed failed", file=sys.stderr)
        return 2

    os.makedirs(DIGEST_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    md = ["# 每周技术摘要 · %s" % today, "",
          "> 来源为公开 RSS/Atom 订阅，每源取前 %d 条，共 %d 条。" % (per_feed, len(collected)),
          "> 由 `tools/digest.py` 自动汇总；摘要为原站点摘要的截断，不是重写。", ""]
    md += ["## 条目", "", "| 来源 | 日期 | 标题 |", "|---|---|---|"]
    for it in collected:
        md.append("| %s | %s | [%s](%s) |" % (
            it["source"], it["date"], it["title"].replace("|", "\\|"), it["link"]))
    md += ["", "## 逐个看", ""]
    for it in collected:
        md.append("### %s" % it["title"])
        md.append("")
        md.append("- 来源：%s · %s" % (it["source"], it["date"]))
        md.append("- 链接：%s" % it["link"])
        md.append("- 摘要：%s" % (it["summary"] or "（该订阅未提供摘要，需点开原文）"))
        md.append("")
    if failed:
        md += ["## 本轮不可达的源", "", "| 源 | 原因 |", "|---|---|"]
        for name, url, why in failed:
            md.append("| %s | %s |" % (name, why.replace("|", "\\|")))
        md.append("")
        md.append("按约定只记录、不绕过：不换 UA、不重试、不走镜像。")
        md.append("")
    digest_path = os.path.join(DIGEST_DIR, "%s.md" % today)
    with open(digest_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    candidates = screen(collected)
    rv = ["# 自我完善候选 · %s" % today, "",
          "> 机械筛选结果：按关键词把上面的条目分到四类，**全部需要人工确认后才动手**。",
          "> 筛选逻辑见 `tools/digest.py` 的 `LEARN_RULES`，宁可多列不可漏列。", ""]
    if candidates:
        rv += ["| 类别 | 条目 |", "|---|---|"]
        for label, title, link in candidates:
            rv.append("| %s | [%s](%s) |" % (label, title.replace("|", "\\|"), link))
    else:
        rv.append("本轮没有命中任何关键词的条目。")
    rv += ["", "## 待确认清单", "",
           "- [ ] 有没有值得直接抄进本仓库 CI 的做法（只看机制，不抄代码）",
           "- [ ] 有没有需要新增的检测规则（对应 `guard/scan-secrets.sh` 的规则表）",
           "- [ ] 有没有需要记进 `docs/` 的坑（失败模式、边界条件）",
           "- [ ] 以上都不成立 → 本文件只作留档，不做任何改动", ""]
    review_path = os.path.join(REVIEW_DIR, "%s.md" % today)
    with open(review_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rv) + "\n")

    print("wrote %s" % os.path.relpath(digest_path, ROOT))
    print("wrote %s" % os.path.relpath(review_path, ROOT))
    print("items=%d failed_feeds=%d candidates=%d" % (len(collected), len(failed), len(candidates)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
