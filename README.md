# 洞察报告 Sourcing —— 咨询/研究观点聚合与每周综述

一个**全自动、免费、可公开访问**的网站：定期从不同咨询/研究机构（麦肯锡、BCG、Gartner、甲子光年、微信公众号等）抓取报告，并用 AI 整理成「每周观点综述」，自动存档、可回溯。

- 🆓 全部跑在 GitHub 免费额度内，无需自己的服务器
- 🔧 零代码日常使用：看报告、加来源都在网页上点
- 🤖 每周一自动抓取 + 生成周报，也可手动一键更新
- 📝 报告全文/摘要 + 周报全部版本化存档

---

## 一、一次性部署（约 10 分钟）

> 下面命令可在本机终端粘贴运行；你也可以让我（WorkBuddy）直接帮你跑。

### 1. 建 GitHub 仓库并推送
```bash
git init
git branch -M main
git add -A
git commit -m "init insight sourcing"
gh repo create insight-sourcing --public --source=. --remote=origin
git push -u origin main
```
（没有 `gh` 也行：在 github.com 新建空仓库，然后 `git remote add origin <地址>` 再 `git push`。）

### 2. 开启 GitHub Pages
仓库 → **Settings → Pages → Build and deployment → Source 选 "Deploy from a branch"**，
Branch 选 **main**，目录(folder)选 **/docs** → Save。
几分钟后网站地址为 `https://<你的用户名>.github.io/insight-sourcing/`。

### 3. 配置 AI Key（用于周报整理）
仓库 → **Settings → Secrets and variables → Actions → New repository secret**
- Name：`DEEPSEEK_API_KEY`
- Value：你的 DeepSeek API Key（在 platform.deepseek.com 注册后「API keys」里创建，几块钱额度可用很久）

> 没配 Key 也能跑：周报会退化为「按分类汇总」的简易版，配了之后自动升级为 AI 观点综述。

### 4. 跑一次（自动抓取+生成+上线）
仓库 → **Actions → 左侧 "每周更新" → Run workflow**。
跑完刷新网站即可看到内容。

### 5. （可选）后台加源用的令牌
打开仓库里的 `admin.html`（本地双击，或部署后访问 `.../admin.html`）：
- 填仓库所有者、仓库名
- 填一个 **Personal Access Token (PAT)**：GitHub → Settings → Developer settings → PAT → 勾选 `repo` 和 `workflow` 权限
- 以后加新来源就在这里填网址提交，自动触发重新抓取

---

## 二、接入微信公众号（甲子光年 / 华泰 / 国泰君安…）

微信公众号本身有反爬，不能直接抓。做法是把它**变成 RSS 源**，再填进 `sources.yaml`（或后台页）：

1. 用一个「公众号转 RSS」服务拿到该公众号的 RSS 地址，常见选择：
   - **RSSHub**：自建或找公共实例，路由如 `/wechat/user/{{ 公众号 id }}`
   - **WeRSS / werss.io** 等SaaS：粘贴公众号主页即可生成 RSS
2. 把拿到的 RSS 地址填到 `sources.yaml` 里 `via: wechat_rss` 的那两条（`REPLACE_WITH_WECHAT_RSS_URL` 替换掉），或直接在 `admin.html` 里加一条、标记「微信公众号」。
3. 图片式长图报告：当前版本只存图片+原文链接，周报引用其标题/摘要；OCR 文字识别为后续扩展（见下）。

---

## 三、日常使用（零代码）

- **看报告 / 周报**：浏览器打开网站，每周一自动更新。
- **加新来源**：打开 `admin.html` → 填名称/网址/分类 → 提交，自动生效并重新抓取。
- **立刻更新**：Actions 页面点一次「Run workflow」。
- **你只需一次性做**：建仓库、填 1 个 AI Key、填 1 个 Token 到后台页。

---

## 四、目录结构

```
sources.yaml        # 来源配置（主要在后台改）
config.yaml         # 全局参数（一般不用改）
scripts/
  fetch.py          # 抓取+结构化+存档
  digest.py         # 生成每周观点综述
  build_site.py     # 生成静态站点
data/
  reports.json      # 报告索引(去重)
  reports/<id>.md   # 单篇报告
  digests/<周>.md   # 每周综述
docs/               # 生成的网站（Pages 从这里发布，GitHub Pages 只支持 / 或 /docs）
admin.html          # 可视化加源后台
.github/workflows/ci.yml  # 定时+手动流水线
```

## 五、常见问题

- **某来源抓不到 / 失效**：周报会自动跳过该源并在站点标注，不影响其他源。检查 `sources.yaml` 里该条的 `url` 是否仍有效。
- **报告只有摘要没有全文**：多数为注册/付费 PDF 或微信长图，属正常；周报基于标题/摘要/可抓文字整理。
- **想改网站标题/副标题**：改 `config.yaml` 的 `site` 段。
- **想加搜索 / 邮件推送 / 图片OCR**：见计划「可后续扩展」。

---

## 六、可后续扩展（非本次必做）

- **图片式报告 OCR**：接入视觉/OCR 模型，把微信长图文字识别出来，使其也能进入周报观点整理。
- 搜索框、邮件/微信订阅推送周报。
- 主题标签云、机构对比视图、本地全文检索（PageFind）。
