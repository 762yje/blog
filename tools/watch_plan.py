#!/usr/bin/env python3
"""Decide which watched tools changed upstream and therefore need a rebuild.

Reads `.state/tool-watch.json` (written by tool-release-watch.yml), asks the
GitHub API for each tool's latest release tag, and prints two workflow outputs:

    selected  逗号分隔的工具名（可能为空字符串 = 本轮无事可做）
    tags      JSON 映射 name -> tag，供 matrix 里 checkout 用 ref

Env: GH_TOKEN, ONLY（可选的逗号列表：给了就强制选中这些工具，无视状态）
"""

import json
import os
import sys
import urllib.request

TOOLS = [
    {"name": "ripgrep", "repo": "BurntSushi/ripgrep"},
    {"name": "fd", "repo": "sharkdp/fd"},
    {"name": "fzf", "repo": "junegunn/fzf"},
    {"name": "jq", "repo": "jqlang/jq"},
]
STATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".state", "tool-watch.json")


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def latest_tag(repo, token):
    req = urllib.request.Request(
        "https://api.github.com/repos/%s/releases/latest" % repo,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "tool-release-watch/1.0",
                 **({"Authorization": "Bearer %s" % token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return (data.get("tag_name") or "").strip()
    except Exception as exc:  # noqa: BLE001
        print("latest_tag(%s)=FAILED %s" % (repo, exc), file=sys.stderr)
        return ""


def emit(name, value):
    print("%s=%s" % (name, value))
    out = os.environ.get("GITHUB_OUTPUT", "")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("%s=%s\n" % (name, value))


def main():
    token = os.environ.get("GH_TOKEN", "")
    state = load_state()
    only = [t.strip() for t in os.environ.get("ONLY", "").split(",") if t.strip()]

    selected, tags = [], {}
    for tool in TOOLS:
        name, repo = tool["name"], tool["repo"]
        if only and name not in only:
            continue
        tag = latest_tag(repo, token)
        if not tag:
            # 查不到就当成"未变化"，不影响其它工具
            print("%s: tag unknown, skipped" % name, file=sys.stderr)
            continue
        tags[name] = tag
        known = (state.get(name) or {}).get("tag")
        if only or known != tag:
            selected.append(name)
            print("%s: %s -> rebuild (state=%s)" % (name, tag, known or "none"))
        else:
            print("%s: %s unchanged" % (name, tag))

    emit("selected", ",".join(selected))
    emit("tags", json.dumps(tags, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
