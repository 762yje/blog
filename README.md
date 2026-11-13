# blog

深海笔记 · 手写静态站，无框架、无构建。托管在 GitHub Pages。

- 线上地址：https://762yje.github.io/blog/
- 源站在 `main` 分支根目录，`index.html` 是列表页，`posts/` 下是文章。

## 加一篇

1. 在 `posts/` 新建 `xxx.html`（复制 `posts/hello.html`，改标题、日期、正文）。
2. 在 `index.html` 的 `<main class="list">` 里加一张卡片，`href="posts/xxx.html"`。
3. 提交推送：

```bash
git add -A && git commit -m "post: xxx" && git push
```

`pages.yml` 会在 push 到 `main` 时自动构建并部署（也可 `gh workflow run pages.yml` 手动触发），约 1 分钟内上线。

## 部署方式

Pages 的 source 设为 **GitHub Actions**（`build_type: workflow`），不使用 jekyll 分支构建：

- `actions/configure-pages@v5` → `actions/upload-pages-artifact@v3`（上传整个仓库根目录）→ `actions/deploy-pages@v4`
- 权限：`contents: read` + `pages: write` + `id-token: write`
- `concurrency: pages`，`cancel-in-progress: false`，不打断正在跑的部署

## 回滚

```bash
git revert <bad-commit> && git push          # 回退内容，自动重新部署
gh workflow run pages.yml                     # 或手动重跑部署
gh api -X DELETE repos/762yje/blog/pages      # 彻底关掉 Pages（站点变 404）
```
## 自动化（Actions）

| 工作流 | 触发 | 干什么 |
|---|---|---|
| `pages.yml` | push main / 手动 | 部署静态站 |
| `guard.yml` | push / PR / 每天 11:17 / 手动 | 用 `dsh-build-lab` 的 `guard/scan-secrets.sh` 扫树+全历史，密钥/PII 命中即失败 |
| `daily-trending.yml` | 每天 08:00（CST） | 抓 GitHub 当日星标增长最快的 10 个新仓库，生成 `posts/trending-<date>.md/.html` 并插卡片 |
| `weekly-digest.yml` | 周二/四/六 09:00（CST） | 抓 6 个公开技术源，生成 `digest/<date>.md` + `docs/self-review/<date>.md` |
| `compile-request.yml` | 手动 | 在 `windows-latest` 上编译公开仓库源码，打包 + sha256，传 Release 并回传下载链接 |
| `tool-release-watch.yml` | 周一 11:00（CST） | 盯 ripgrep / fd / fzf / jq 的上游 tag，变了自己编译成 Windows 免安装版（jq 走 MSYS2 UCRT64 autotools），传私库 `tools-latest` 并同步 `tools/manifest.json` |
| `housekeeping.yml` | 每月 1 日 12:00（CST） | 清 30 天前的 Artifacts、旧 run、旧 `build-*` release（保留最近 3 个） |
| `notify.yml` | 被上面几个 `workflow_call` | 邮件通知；同一工作流连续失败 3 次升级成 `[ALERT]` |

本机手动跑一次：

```bash
gh workflow run daily-trending.yml -R 762yje/blog
gh workflow run weekly-digest.yml  -R 762yje/blog
gh run list -R 762yje/blog --limit 5
```

本地预览生成器（不联网写入远端）：

```bash
GH_TOKEN=$(gh auth token) python3 tools/trending.py
python3 tools/digest.py
```

## 通知（邮件）

通道已收敛为**邮件**一项（Server酱 / PushPlus 已下线）。配齐下列 Secrets 即可收信，成功与失败都发：

| Secret | 说明 |
|---|---|
| `NOTIFY_SMTP_HOST` | SMTP 服务器，如 `smtp.qq.com` |
| `NOTIFY_SMTP_PORT` | 端口，缺省 465（465 走 `SMTP_SSL`，其他端口走 STARTTLS） |
| `NOTIFY_SMTP_USER` | 登录账号（通常就是发件地址） |
| `NOTIFY_SMTP_PASS` | 邮箱授权码（不是登录密码） |
| `NOTIFY_SMTP_TO` | 收件地址，多个用英文逗号分隔 |
| `NOTIFY_SMTP_FROM` | 可选，发件人显示地址，缺省同 `NOTIFY_SMTP_USER` |

降级规则：邮件未配或发送失败 → 改为建一条带 `notify` 标签的 GitHub Issue（零配置通道，消息不丢）；两者都不成只打日志，通知失败绝不会把业务工作流判成 failure。同一工作流连续失败 3 次，主题加 `[ALERT]` 后计数归零防轰炸。