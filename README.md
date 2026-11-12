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
| `tool-release-watch.yml` | 周一 11:00（CST） | 盯 ripgrep / fd / fzf 的 tag，变了自己编译成 Windows 免安装版，传私库 `tools-latest` |
| `housekeeping.yml` | 每月 1 日 12:00（CST） | 清 30 天前的 Artifacts、旧 run、旧 `build-*` release（保留最近 3 个） |
| `notify.yml` | 被上面几个 `workflow_call` | 推送结果；同一工作流连续失败 3 次升级成 `[ALERT]` issue（+ 邮件，若配了 SMTP） |

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

## 通知（可选）

`notify.yml` 里任一通道没配也不影响其它通道：GitHub Issue 通道零配置可用，Server酱 / PushPlus / 邮件各自需要同名 Secrets（见仓库 Actions 设置）。