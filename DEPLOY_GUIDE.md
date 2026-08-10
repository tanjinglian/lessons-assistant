# 前事鉴 · Vercel 部署指南

## 一、前提

- GitHub 账号
- Vercel 账号（用GitHub 登录即可，免费）
- DeepSeek API Key（可选，没有也能用，只是提炼功能降级为本地规则）

---

## 二、操作步骤

### 第 1 步：推送代码到 GitHub

```bash
# 进入 Vercel 适配版目录
cd app_vercel

# 初始化 Git
git init
git add .
git commit -m "init: 前事鉴 Vercel 适配版"

# 在 GitHub 网页上创建一个新仓库（如 pitfall-assistant）
# 然后关联并推送：
git remote add origin https://github.com/你的用户名/pitfall-assistant.git
git branch -M main
git push -u origin main
```

### 第 2 步：登录 Vercel 并导入项目

1. 打开 https://vercel.com → 点右上角 **Sign Up** 或 **Log In**
2. 选择 **Continue with GitHub**
3. 登录后点击 **Add New…** → **Project**
4. 在 **Import Git Repository** 列表中找到你刚推送的仓库
5. 点击 **Import**

### 第 3 步：配置项目

在导入配置页面：

| 配置项 | 填写 |
|--------|------|
| Framework Preset | **Other** |
| Root Directory | `.` （默认，不需要改） |
| Build Command | 留空 |
| Output Directory | 留空 |

### 第 4 步：添加环境变量

在同一页面的 **Environment Variables** 区域，添加：

| Key | Value |
|-----|-------|
| `DEEPSEEK_API_KEY` | `sk-你的密钥` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | `deepseek-chat` |

> 如果暂时没有 DeepSeek Key，可以不填，系统会自动降级为本地规则提炼。

### 第 5 步：点击 Deploy

点击 **Deploy** 按钮，等待 30-60 秒构建完成。

成功后你会得到一个地址：
```
https://pitfall-assistant-xxx.vercel.app
```

**浏览器打开这个地址，就能看到前事鉴界面了！**

---

## 三、后续更新

每次修改代码后：

```bash
git add .
git commit -m "update: 描述你的修改"
git push
```

Vercel 会自动重新部署，无需手动操作。

---

## 四、绑定自定义域名（可选）

1. 在 Vercel Dashboard → 你的项目 → **Settings** → **Domains**
2. 添加你的域名（如 `pitfall.yourdomain.com`）
3. 按提示在域名管理处添加 CNAME 记录指向 `cname.vercel-dns.com`
4. 等待 DNS 生效（几分钟），自动签发 HTTPS 证书

---

## 五、重要说明

### 数据持久化

⚠️ Vercel Serverless 版使用 `/tmp/pitfall.db`（SQLite），**每次冷启动后数据会清空**。

对于简历展示场景，这完全可以接受——面试官只需看到功能正常运行即可。

如果需要持久数据，有两种升级路径：
1. **Vercel Postgres**（免费层256MB）——需要改代码把 SQLite 换成 Postgres
2. **Turso**（SQLite 云版本，免费层 9GB）——改动最小，只换连接方式

### 性能

- 首次冷启动约 1-3 秒（Python Runtime 初始化）
- 热状态下请求响应 < 200ms
- 比Render 的 30-60 秒冷启动好得多

### 费用

完全免费（Vercel Hobby Plan）：
- 100GB 带宽/月
- Serverless Function 调用次数无限制
- 自动 HTTPS

---

## 六、简历上怎么写

```
前事鉴 — 职场经验管理与智能检索系统
技术栈：Vue3 + FastAPI (Serverless) + SQLite FTS5+ DeepSeek LLM
功能：记录职场经验 → 全文语义检索 → LLM 智能提炼 → 关联提醒
在线演示：https://pitfall-assistant-xxx.vercel.app
源码：https://github.com/xxx/pitfall-assistant
```

---

## 七、如果遇到问题

| 问题 | 解决 |
|------|------|
| 部署失败 "No Python runtime found" | 确认 `requirements.txt` 在项目根目录 |
| 404 错误 | 确认 `vercel.json` 路由配置正确 |
| API 返回 500 | 检查 Vercel Dashboard → Logs看具体错误 |
| 前端能打开但 API 报错 | 检查环境变量是否正确配置 |
