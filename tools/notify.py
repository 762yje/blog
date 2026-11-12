#!/usr/bin/env python3
"""Notify step for scheduled workflows.

Channels are opt-in: a channel is used only when its secret is present, so the
repository stays green before the operator picks one. Consequences:

  * ServerChan            secrets.NOTIFY_SCT_KEY
  * PushPlus              secrets.NOTIFY_PUSHPLUS_TOKEN
  * GitHub Issue          always available (uses the built-in token)
  * Email on escalation   secrets.NOTIFY_SMTP_HOST / PORT / USER / PASS / TO

Streak rule: every failure increments a per-workflow counter stored in
`.notify/state.json`; three consecutive failures escalate (issue + email) and
reset the counter so an already-reported incident does not spam.

Env: STATUS, WF_NAME, TITLE, MESSAGE, RUN_URL, GITHUB_REPOSITORY, GH_TOKEN,
     SCT_KEY, PUSHPLUS_TOKEN, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_TO
"""

import json
import os
import smtplib
import sys
import urllib.parse
import urllib.request
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, ".notify", "state.json")
ESCALATE_AT = 3
FAIL_WORDS = ("failure", "cancelled", "timed_out")


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"workflows": {}}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def post_form(url, fields, timeout=20):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "blog-notify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()[:200].decode("utf-8", "replace")


def post_json(url, payload, timeout=20):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "blog-notify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()[:200].decode("utf-8", "replace")


def send_serverchan(title, body):
    key = os.environ.get("SCT_KEY", "").strip()
    if not key:
        return None
    try:
        status, text = post_form("https://sctapi.ftqq.com/%s.send" % key,
                                 {"title": title, "desp": body})
        print("serverchan=http_%s %s" % (status, text))
        return True
    except Exception as exc:  # noqa: BLE001
        print("serverchan=FAILED %s" % exc, file=sys.stderr)
        return False


def send_pushplus(title, body):
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        return None
    try:
        status, text = post_json("https://www.pushplus.plus/send",
                                 {"token": token, "title": title,
                                  "content": body, "template": "txt"})
        print("pushplus=http_%s %s" % (status, text))
        return True
    except Exception as exc:  # noqa: BLE001
        print("pushplus=FAILED %s" % exc, file=sys.stderr)
        return False


def send_issue(title, body, labels):
    """Issue channel: needs gh CLI (present on GitHub runners) and GH_TOKEN."""
    import subprocess
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not repo or not token:
        return None
    cmd = ["gh", "issue", "create", "-R", repo, "--title", title, "--body", body]
    for label in labels:
        cmd += ["--label", label]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                             env={**os.environ, "GH_TOKEN": token})
        if out.returncode == 0:
            print("issue=%s" % out.stdout.strip())
            return True
        print("issue=FAILED %s" % (out.stderr.strip()[:300]), file=sys.stderr)
        return False
    except Exception as exc:  # noqa: BLE001
        print("issue=FAILED %s" % exc, file=sys.stderr)
        return False


def send_mail(subject, body):
    host = os.environ.get("SMTP_HOST", "").strip()
    to_addr = os.environ.get("SMTP_TO", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    if not (host and to_addr and user and password):
        return None
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        port = int(os.environ.get("SMTP_PORT", "465"))
        if port == 465:
            client = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            client = smtplib.SMTP(host, port, timeout=30)
            client.starttls()
        client.login(user, password)
        client.send_message(msg)
        client.quit()
        print("mail=sent")
        return True
    except Exception as exc:  # noqa: BLE001
        print("mail=FAILED %s" % exc, file=sys.stderr)
        return False


def main():
    status = (os.environ.get("STATUS") or "unknown").strip().lower()
    wf = (os.environ.get("WF_NAME") or "unknown-workflow").strip()
    title = (os.environ.get("TITLE") or "").strip()
    message = (os.environ.get("MESSAGE") or "").strip()
    run_url = (os.environ.get("RUN_URL") or "").strip()

    failed = any(w in status for w in FAIL_WORDS)

    state = load_state()
    entry = state["workflows"].setdefault(wf, {"failures": 0})
    entry["failures"] = entry.get("failures", 0) + 1 if failed else 0
    entry["last_status"] = status
    entry["last_run"] = run_url
    entry["updated"] = os.environ.get("GITHUB_RUN_ID", "")
    streak = entry["failures"]
    escalate = failed and streak >= ESCALATE_AT
    if escalate:
        entry["failures"] = 0
        entry["last_escalation"] = run_url

    head = title or ("%s %s" % (wf, status))
    body = "\n".join(x for x in [
        "工作流：%s" % wf,
        "结果：%s（连续失败 %d 次）" % (status, streak),
        message,
        "运行：%s" % run_url,
    ] if x)

    sent = []
    if not failed:
        for fn, name in ((send_serverchan, "serverchan"), (send_pushplus, "pushplus")):
            if fn(head, body):
                sent.append(name)
    else:
        for fn, name in ((send_serverchan, "serverchan"), (send_pushplus, "pushplus")):
            if fn(head, body):
                sent.append(name)
        if send_issue(head, body, ["notify"]):
            sent.append("issue")
        if escalate:
            if send_issue("[ALERT] %s 连续失败 %d 次" % (wf, streak),
                          body + "\n\n这已经是第 %d 次连续失败，按约定升级报警。" % streak,
                          ["notify", "alert"]):
                sent.append("issue-alert")
            if send_mail("[ALERT] %s 连续失败 %d 次" % (wf, streak), body):
                sent.append("mail-alert")

    print("STATUS=%s streak=%d escalate=%s channels=%s"
          % (status, streak, str(escalate).lower(), ",".join(sent) or "none"))

    save_state(state)
    print("CHANGED=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
