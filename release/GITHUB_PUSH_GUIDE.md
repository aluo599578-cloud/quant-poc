# 推到 GitHub 的一键脚本

这个脚本帮你把 quant-poc 推到 https://github.com/alor27/quant-poc

## 使用方法

打开 PowerShell（管理员），运行：

```powershell
cd C:\Users\18566\Desktop\quant-poc

# 1. 确认 remote 已加
git remote -v
# 应该看到 origin https://github.com/alor27/quant-poc.git

# 2. 推送
git push -u origin main
```

## 如果弹出凭证框

- Username: `alor27`
- Password: **粘贴你的 GitHub Personal Access Token**（不是 GitHub 密码）

⚠️ GitHub 已经不支持密码登录，必须用 PAT。
PAT 生成：https://github.com/settings/tokens/new

## 如果你已经在 GitHub 创建好了仓库

仓库地址：https://github.com/alor27/quant-poc
- Public 还是 Private 由你选

## 如果你还没创建仓库

打开 https://github.com/new：
- Repository name: `quant-poc`
- Description: `A 股量化研究 PoC - TradingView → PaperEngine → Streamlit`
- ⚠️ 不要勾选 "Add a README" / "Add .gitignore" / "Choose a license"（本地都有了）
- 选 Public 或 Private
- Create repository

## 推完后做这两件事

### A. 创建 GitHub Release v0.1.0

打开 https://github.com/alor27/quant-poc/releases/new

- Choose tag: 填 `v0.1.0` → Create new tag
- Release title: `v0.1.0 — 首次发布`
- Description: 复制粘贴 `RELEASE_NOTES.md` 内容
- 上传附件：`release/quant-poc-release.zip`（拖拽进去）
- Publish release

### B. 启用 GitHub Pages（可选，展示 dashboard）

打开 https://github.com/alor27/quant-poc/settings/pages

- Source: Deploy from a branch
- Branch: `main` / `/root`
- Save

几分钟后访问 https://alor27.github.io/quant-poc/release/quant-dashboard-static.html

## 常见问题

### Q: remote 已存在但 push 失败

```
git remote remove origin
git remote add origin https://github.com/alor27/quant-poc.git
```

### Q: 仓库已经存在但 git log 不一样

如果 GitHub 仓库有 README，push 会被拒绝。先 pull：

```powershell
git pull origin main --allow-unrelated-histories
git push -u origin main
```

### Q: 凭证缓存（Windows）

第一次 push 后 git 会缓存 PAT，下次不用重输。如果要清除：

```powershell
git credential-manager clear
# 或
git config --global --unset credential.helper
```
