#!/usr/bin/env python3
"""Merge per-tool build reports into `.state/tool-watch.json`.

Input: a directory of `report/<tool>.json` files produced by the build matrix
(each has name / repo / tag / exe_path / asset / sha256 / size / uploaded).
Only successful legs write a report, so a failed leg keeps its old state entry
and gets retried on the next run.

Outputs: changed=true|false, summary=「ripgrep 15.2.0, jq 1.8.2」
"""

import argparse
import datetime
import glob
import json
import os
import sys


def emit(name, value):
    out = os.environ.get("GITHUB_OUTPUT", "")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("%s=%s\n" % (name, value))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--state", default=".state/tool-watch.json")
    args = ap.parse_args()

    try:
        with open(args.state, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    built, changed = [], False
    for path in sorted(glob.glob(os.path.join(args.reports, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
        name, tag = report.get("name"), report.get("tag")
        if not name or not tag:
            continue
        entry = {
            "tag": tag,
            "repo": report.get("repo", ""),
            "exe_path": report.get("exe_path", ""),
            "asset": report.get("asset", ""),
            "sha256": report.get("sha256", ""),
            "size": report.get("size", 0),
            "uploaded": bool(report.get("uploaded")),
            "updated_at": now,
        }
        if state.get(name) != entry:
            state[name] = entry
            changed = True
        built.append("%s %s" % (name, tag))

    if changed:
        os.makedirs(os.path.dirname(args.state), exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")

    summary = ", ".join(built) if built else "无新增构建"
    emit("changed", "true" if changed else "false")
    emit("summary", summary)
    emit("built", ";".join(built))
    print("changed=%s summary=%s" % (changed, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
