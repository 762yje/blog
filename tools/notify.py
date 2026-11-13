#!/usr/bin/env python3
"""Notify step for the scheduled workflows — email is the only delivery channel.

Required Secrets (all optional; email is used only when they are complete):

    NOTIFY_SMTP_HOST    SMTP 服务器，例如 smtp.qq.com / smtp.163.com
    NOTIFY_SMTP_PORT    465（SSL）或 587（STARTTLS）；缺省 465
    NOTIFY_SMTP_USER    发信账号（通常是完整邮箱地址）
    NOTIFY_SMTP_PASS    授权码 / 应用专用密码（不是登录密码）
    NOTIFY_SMTP_TO      收件地址
    NOTIFY_SMTP_FROM    可选，缺省等于 SMTP_USER

Degradation when email is not configured (or the send fails):

  1. GitHub Issue —— 零配置通道，用仓库自带的 token 建一条 issue，消息不丢。
  2. Issue 也失败：打印 `mail=unconfigured/unavailable issue=FAILED` 并 exit 0，
     绝不因为通知失败把工作流判成失败（通知是旁路，不是主任务）。

三个连续失败升级：同一工作流连败 3 次，主题加 `[ALERT]` 前缀、正文多一行升级说明，
然后计数归零，避免已经报过的问题反复轰炸。

Env: STATUS, WF_NAME, TITLE, MESSAGE, RUN_URL, GITHUB_REPOSITORY, GH_TOKEN,
     SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_TO, SMTP_FROM
"""

import json
import os
import smtplib
import sys
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, ".notify", "state.json")
ESCALATE_AT = 3
FAIL_WORDS = ("failure", "cancelled", "canceled", "timed_out", "timed_out")


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


def mail_config():
    """Return (config, problems). config is None when email cannot be used."""
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    to_addr = os.environ.get("SMTP_TO", "").strip()
    missing = [name for name, value in
               (("SMTP_HOST", host), ("SMTP_USER", user),
                ("SMTP_PASS", password), ("SMTP_TO", to_addr)) if not value]
    if missing:
        return None, missing
    return {
        "host": host,
        "port": int(os.environ.get("SMTP_PORT", "465") or 465),
        "user": user,
        "password": password,
        "to": [a.strip() for a in to_addr.split(",") if a.strip()],
        "sender": (os.environ.get("SMTP_FROM", "").strip() or user),
    }, []


def send_mail(subject, body, cfg):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(cfg["to"])
    msg.set_content(body)
    try:
        if cfg["port"] == 465:
            client = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30)
        else:
            client = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
            client.starttls()
        client.login(cfg["user"], cfg["password"])
        client.send_message(msg)
        client.quit()
        print("mail=sent to=%s" % ",".join(cfg["to"]))
        return True
    except Exception as exc:  # noqa: BLE001
        print("mail=FAILED %s" % exc, file=sys.stderr)
        return False


def send_issue(subject, body, labels):
    """Fallback channel: needs gh CLI (present on runners) and GH_TOKEN."""
    import subprocess
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not repo or not token:
        print("issue=unconfigured (no repo/token)", file=sys.stderr)
        return False
    cmd = ["gh", "issue", "create", "-R", repo, "--title", subject, "--body", body]
    for label in labels:
        cmd += ["--label", label]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                             env={**os.environ, "GH_TOKEN": token})
        if out.returncode == 0:
            print("issue=%s" % out.stdout.strip())
            return True
        print("issue=FAILED %s" % out.stderr.strip()[:300], file=sys.stderr)
        return False
    except Exception as exc:  # noqa: BLE001
        print("issue=FAILED %s" % exc, file=sys.stderr)
        return False


def main():
    status = (os.environ.get("STATUS") or "unknown").strip().lower()
    wf = (os.environ.get("WF_NAME") or "unknown-workflow").strip()
    title = (os.environ.get("TITLE") or "").strip()
    message = (os.environ.get("MESSAGE") or "").strip()
    run_url = (os.environ.get("RUN_URL") or "").strip()

    failed = any(word in status for word in FAIL_WORDS)

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

    subject = title or ("%s %s" % (wf, status))
    if escalate:
        subject = "[ALERT] %s" % subject
    body = "\n".join(x for x in [
        "工作流：%s" % wf,
        "结果：%s（连续失败 %d 次）" % (status, streak),
        message,
        "运行：%s" % run_url,
        "" ,
        "这封邮件由 blog 仓库的 notify 工作流发出；回复无效。",
    ] if x)
    if escalate:
        body += "\n\n这已经是连续第 %d 次失败，按约定升级报警。" % ESCALATE_AT

    cfg, missing = mail_config()
    delivered = []
    if cfg:
        if send_mail(subject, body, cfg):
            delivered.append("mail")
    else:
        print("mail=unconfigured missing=%s — 降级到 GitHub Issue"
              % ",".join(missing), file=sys.stderr)

    if not delivered:
        labels = ["notify", "alert"] if escalate else ["notify"]
        if send_issue(subject, body, labels):
            delivered.append("issue")

    print("STATUS=%s streak=%d escalate=%s channels=%s"
          % (status, streak, str(escalate).lower(), ",".join(delivered) or "none"))
    save_state(state)
    print("CHANGED=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
