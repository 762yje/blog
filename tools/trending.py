#!/usr/bin/env python3
"""Generate the daily "hottest open-source projects" post.

Data source: the official GitHub REST API (/search/repositories).
No web-page scraping, no third-party endpoints, no credentials in this file.

Env:
  GH_TOKEN     token for the API (optional; unauthenticated = 10 req/min)
  WINDOW_DAYS  created-within window, default 7
  MIN_STARS    star floor used in the query, default 100
  LIMIT        number of projects, default 10

Outputs:
  posts/trending-<date>.md    markdown source of the post
  posts/trending-<date>.html  rendered page served by GitHub Pages
  index.html                  newest trending card prepended, older ones pruned
"""

import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "posts")
INDEX_HTML = os.path.join(ROOT, "index.html")
API = "https://api.github.com/search/repositories"
KEEP_CARDS = 5


def api_get(url, token, attempts=3):
    for i in range(attempts):
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "blog-trending-generator",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if token:
            req.add_header("Authorization", "Bearer %s" % token)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read()[:400].decode("utf-8", "replace")
            print("HTTP %s on attempt %d: %s" % (exc.code, i + 1, body), file=sys.stderr)
            if exc.code in (403, 429):
                time.sleep(20 * (i + 1))
                continue
            if exc.code >= 500:
                time.sleep(5 * (i + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            print("network error on attempt %d: %s" % (i + 1, exc), file=sys.stderr)
            time.sleep(5 * (i + 1))
    raise SystemExit("gave up after %d attempts: %s" % (attempts, url))


def collect(token, window_days, min_stars, limit):
    since = (dt.date.today() - dt.timedelta(days=window_days)).isoformat()
    q = "created:>=%s stars:>=%d fork:false archived:false" % (since, min_stars)
    url = API + "?" + urllib.parse.urlencode({
        "q": q, "sort": "stars", "order": "desc", "per_page": str(limit),
    })
    data = api_get(url, token)
    items = []
    for repo in data.get("items", [])[:limit]:
        items.append({
            "name": repo.get("full_name") or "",
            "url": repo.get("html_url") or "",
            "desc": (repo.get("description") or "").strip(),
            "stars": repo.get("stargazers_count") or 0,
            "lang": repo.get("language") or "n/a",
            "topics": [t for t in (repo.get("topics") or [])][:6],
            "created": (repo.get("created_at") or "")[:10],
        })
    if not items:
        raise SystemExit("API returned no repositories for query: %s" % q)
    return items, since


def render_markdown(items, day, since):
    lines = [
        "# 今日热门开源项目 · %s" % day,
        "",
        "> 数据来源：GitHub REST API 搜索接口，`created:>=%s`、按 star 数排序。" % since,
        "> 由 `tools/trending.py` 自动生成，每天 08:00（Asia/Shanghai）更新。",
        "",
        "| # | 项目 | 语言 | Stars | 简介 |",
        "|---|---|---|---|---|",
    ]
    for i, it in enumerate(items, 1):
        desc = it["desc"].replace("|", "\\|") or "（无描述）"
        lines.append("| %d | [%s](%s) | %s | %d | %s |" % (
            i, it["name"], it["url"], it["lang"], it["stars"], desc))
    lines += ["", "## 逐个看", ""]
    for i, it in enumerate(items, 1):
        lines.append("### %d. %s" % (i, it["name"]))
        lines.append("")
        lines.append("- 链接：%s" % it["url"])
        lines.append("- 语言 / Stars：%s / %d" % (it["lang"], it["stars"]))
        if it["topics"]:
            lines.append("- 标签：%s" % ", ".join(it["topics"]))
        lines.append("- 简介：%s" % (it["desc"] or "（仓库未填写描述）"))
        lines.append("")
    return "\n".join(lines) + "\n"


HTML_HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>
  :root{--abyss:#04101d;--deep:#081a2c;--edge:#16436b;--glow:#7fd7ff;--text:#c9dbe8;--dim:#6f8ca4}
  *{box-sizing:border-box}
  body{margin:0;background:linear-gradient(180deg,var(--deep) 0%%,var(--abyss) 55%%,#02090f 100%%);
       color:var(--text);font:16px/1.75 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif}
  .wrap{max-width:760px;margin:0 auto;padding:72px 24px 96px}
  .kicker{color:var(--glow);letter-spacing:.32em;text-transform:uppercase;font-size:12px;opacity:.85}
  h1{font-size:30px;line-height:1.25;margin:14px 0 10px;color:#eaf6ff;font-weight:600}
  .sub{color:var(--dim);font-size:14px}
  .rule{height:1px;margin:36px 0;background:linear-gradient(90deg,var(--edge),transparent)}
  .card{background:linear-gradient(180deg,rgba(20,58,92,.55),rgba(8,26,44,.55));border:1px solid var(--edge);
        border-radius:14px;padding:18px 20px;margin:0 0 16px}
  .card h2{margin:0 0 6px;font-size:18px;color:#e6f4ff}
  .card p{margin:0 0 8px;color:var(--dim);font-size:14px}
  .card .tags{color:var(--glow);font-size:12px;letter-spacing:.06em;text-transform:uppercase}
  a{color:var(--glow);text-decoration:none}
  footer{margin-top:64px;padding-top:24px;border-top:1px solid var(--edge);color:var(--dim);font-size:13px}
</style>
</head>
<body>
<div class="wrap">
"""


def render_html(items, day, since, post_path):
    esc = html.escape
    out = [HTML_HEAD % esc("今日热门开源项目 · " + day)]
    out.append('  <div class="kicker">daily trending</div>\n')
    out.append("  <h1>今日热门开源项目 · %s</h1>\n" % esc(day))
    out.append('  <p class="sub">GitHub 上 %s 之后新建、按 star 数排名的前 %d 个项目。'
               '数据取自 GitHub REST API。</p>\n' % (esc(since), len(items)))
    out.append('  <div class="rule"></div>\n')
    for it in items:
        out.append('  <div class="card">\n')
        out.append('    <div class="tags">%s · %s · ★%d</div>\n'
                   % (esc(it["lang"]), esc(it["created"] or day), it["stars"]))
        out.append('    <h2><a href="%s">%s</a></h2>\n' % (esc(it["url"]), esc(it["name"])))
        out.append('    <p>%s</p>\n' % esc(it["desc"] or "（仓库未填写描述）"))
        out.append('  </div>\n')
    out.append('  <footer>自动生成 · <a href="../index.html">返回首页</a> · '
               '源文件 <code>%s</code></footer>\n' % esc(post_path))
    out.append("</div>\n</body>\n</html>\n")
    return "".join(out)


CARD_RE = re.compile(
    r'\n\s*<a class="card" href="posts/trending-[^"]*">.*?</a>', re.S)


def update_index(day, title, summary, post_path):
    with open(INDEX_HTML, encoding="utf-8") as fh:
        page = fh.read()
    marker = '<main class="list">'
    if marker not in page:
        raise SystemExit("index.html has no <main class=\"list\"> marker")
    card = (
        '\n    <a class="card" href="%s">'
        '\n      <div class="meta"><span>%s</span><span>·</span><span>自动日报</span></div>'
        '\n      <h2>%s</h2>'
        '\n      <p>%s</p>'
        '\n    </a>'
    ) % (post_path, day, html.escape(title), html.escape(summary))
    body = CARD_RE.sub("", page)
    newest = [c for c in CARD_RE.findall(body)]
    keep = newest[:KEEP_CARDS - 1]
    body = CARD_RE.sub("", body)
    rebuilt = "".join(keep) + card
    page = body.replace(marker, marker + rebuilt, 1)
    with open(INDEX_HTML, "w", encoding="utf-8") as fh:
        fh.write(page)
    return len(keep) + 1


def main():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    window_days = int(os.environ.get("WINDOW_DAYS", "7"))
    min_stars = int(os.environ.get("MIN_STARS", "100"))
    limit = int(os.environ.get("LIMIT", "10"))

    day = dt.date.today().isoformat()
    items, since = collect(token, window_days, min_stars, limit)

    md_name = "trending-%s.md" % day
    html_name = "trending-%s.html" % day
    md_path = os.path.join(POSTS_DIR, md_name)
    html_path = os.path.join(POSTS_DIR, html_name)
    os.makedirs(POSTS_DIR, exist_ok=True)

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(items, day, since))
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(items, day, since, "posts/" + md_name))

    top = items[0]
    summary = "%s 领跑（★%d）；其余 %d 个见正文。" % (
        top["name"], top["stars"], max(0, len(items) - 1))
    cards = update_index(day, "今日热门开源项目 · " + day, summary,
                         "posts/" + html_name)

    print("wrote %s (%d bytes)" % (md_name, os.path.getsize(md_path)))
    print("wrote %s (%d bytes)" % (html_name, os.path.getsize(html_path)))
    print("index.html cards for trending: %d" % cards)
    print("top=%s stars=%d" % (top["name"], top["stars"]))


if __name__ == "__main__":
    main()
