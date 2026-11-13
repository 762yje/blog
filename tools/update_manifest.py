#!/usr/bin/env python3
"""Patch one entry of the private tool manifest through the GitHub contents API.

只改一个工具那一条 + 顶层 updated_at，其余内容原样保留；写失败（409 = 别人先提交了）
会自动重读再写，最多 3 次。不改本地文件，避免在公库 runner 上留私库副本。

用法：
    python3 tools/update_manifest.py \
        --name ripgrep --version 15.2.0 \
        --asset dsh-ripgrep-15.2.0-windows-x64.zip \
        --sha256 <hex> --size 1789611 --exe-path rg.exe \
        [--repo-source BurntSushi/ripgrep] [--target 762yje/dsh-cloud] \
        [--path tools/manifest.json] [--release-tag tools-latest]

Env: GH_TOKEN（对目标仓库有 contents:write 的 token）
"""

import argparse
import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def request(method, url, token, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer %s" % token,
        "User-Agent": "tool-release-watch/1.0",
        "Content-Type": "application/json",
    })
    return urllib.request.urlopen(req, timeout=30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=os.environ.get("PRIVATE_REPO", "762yje/dsh-cloud"))
    ap.add_argument("--path", default="tools/manifest.json")
    ap.add_argument("--report", default="",
                    help="build 产出的 report/<tool>.json；给了就覆盖单字段参数")
    ap.add_argument("--name", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--asset", default="")
    ap.add_argument("--sha256", default="")
    ap.add_argument("--size", default=None, type=int)
    ap.add_argument("--exe-path", default="")
    ap.add_argument("--repo-source", default="")
    ap.add_argument("--release-tag", default="tools-latest")
    ap.add_argument("--message", default="")
    args = ap.parse_args()

    if args.report:
        try:
            with open(args.report, encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, ValueError) as exc:
            print("report unreadable: %s" % exc, file=sys.stderr)
            return 2
        if not report.get("uploaded"):
            print("skip %s: 资产未上传（dry-run 或上传失败）" % args.report)
            return 0
        args.name = report.get("name", "")
        args.version = report.get("tag", "")
        args.asset = report.get("asset", "")
        args.sha256 = report.get("sha256", "")
        args.size = report.get("size", 0)
        args.exe_path = report.get("exe_path", "")
        args.repo_source = report.get("repo", "")
        if args.version and str(args.version).startswith("jq-"):
            args.version = str(args.version)[3:]

    missing = [k for k in ("name", "version", "asset", "sha256", "exe_path")
               if not getattr(args, k.replace("-", "_"))]
    if missing:
        print("缺少参数: %s" % ", ".join(missing), file=sys.stderr)
        return 2

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("GH_TOKEN missing", file=sys.stderr)
        return 2

    url = "%s/repos/%s/contents/%s" % (API, args.target, args.path)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for attempt in range(1, 4):
        try:
            with request("GET", url, token) as resp:
                current = json.load(resp)
        except urllib.error.HTTPError as exc:
            print("GET failed: %s" % exc, file=sys.stderr)
            return 2

        try:
            manifest = json.loads(base64.b64decode(current["content"]).decode("utf-8"))
        except (KeyError, ValueError) as exc:
            print("manifest unreadable: %s" % exc, file=sys.stderr)
            return 2

        tools = manifest.setdefault("tools", [])
        entry = None
        for item in tools:
            if item.get("name") == args.name:
                entry = item
                break
        if entry is None:
            entry = {"name": args.name,
                     "asset_pattern": "*" + args.asset.split(args.name, 1)[-1]}
            tools.append(entry)

        entry.update({
            "name": args.name,
            "exe_path": args.exe_path,
            "version": args.version,
            "sha256": args.sha256.lower(),
            "size": args.size,
            "updated_at": now,
            "asset": args.asset,
        })
        if args.repo_source:
            entry["repo"] = args.repo_source
        manifest["release_tag"] = args.release_tag
        manifest["updated_at"] = now

        payload = {
            "message": args.message or "chore(tools): %s %s" % (args.name, args.version),
            "content": base64.b64encode(
                (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            ).decode("ascii"),
            "sha": current["sha"],
        }
        try:
            with request("PUT", url, token, payload) as resp:
                result = json.load(resp)
            print("manifest updated: %s (%s)" % (args.name, result["commit"]["sha"][:8]))
            return 0
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode("utf-8", "replace")
            print("PUT attempt %d failed: %s %s" % (attempt, exc, detail), file=sys.stderr)
            if exc.code in (409, 422):
                continue
            return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
