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
