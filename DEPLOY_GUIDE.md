# 前事鉴 Vercel 部署指南（RAG 版）

## 架构说明

- **前端**：静态 HTML，Vercel 自动托管（`public/index.html`）
- **后端**：Python Serverless Function（`api/index.py`）
- **数据库**：Supabase（PostgreSQL + pgvector 向量检索）
- **Embedding**：智谱 AI `embedding-3`（2048 维向量）
- **LLM**：DeepSeek `deepseek-chat`（经验提炼 + RAG 回答）

---

## 部署步骤

### 第 1 步：配置 Supabase（数据库）

1. 打开 https://supabase.com → 注册/登录
2. **New Project** → 填写名称、数据库密码、选区域
3. 等待项目创建完成（约 1 分钟）
4. 进入项目 → 左侧 **SQL Editor** → 新建查询
5. 把 `supabase_init.sql` 文件的全部内容粘贴进去 → 点 **Run**
6. 进入 **Settings → API**，复制：
   - `Project URL`（如 `https://xxxxx.supabase.co`）
   - `anon public` Key（以 `eyJ` 开头的长字符串）

### 第 2 步：获取智谱 AI API Key

1. 打开 https://open.bigmodel.cn → 登录
2. 进入控制台 → **API Keys** → **创建 API Key**
3. 复制密钥（格式如 `xxxxxxxx.yyyyyyyy`）

### 第 3 步：获取 DeepSeek API Key（如已有可跳过）

1. 打开 https://platform.deepseek.com → 登录
2. **API Keys** → 创建 → 复制

### 第 4 步：在 Vercel 配置环境变量

1. 打开 Vercel Dashboard → 你的项目 → **Settings** → **Environment Variables**
2. 添加以下变量：

| Key | Value |
|-----|-------|
| `ZHIPU_API_KEY` | 智谱 AI 的 API Key |
| `DEEPSEEK_API_KEY` | DeepSeek 的 API Key |
| `SUPABASE_URL` | Supabase 的 Project URL |
| `SUPABASE_KEY` | Supabase 的 anon public key |

3. 点 Save

### 第 5 步：重新部署

配置完环境变量后，进入 **Deployments** 页面 → 点最新一次部署右侧 **⋯** → **Redeploy**

等待 30-60 秒部署完成即可。

---

## 验证

1. 访问 `https://你的项目.vercel.app`
2. 在「今日记录」中保存一条记录 → 应看到 AI 提炼的经验候选
3. 确认经验后，在经验库中应能看到
4. 在「语义搜索」中输入相关词 → 应返回 RAG 回答 + 相似经验来源

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 保存记录报 500 | Supabase 未建表或环境变量错误 | 检查 SQL 是否执行成功、环境变量是否正确 |
| 语义搜索无结果 | 经验库为空或 Embedding 未生成 | 先添加几条经验，确保 ZHIPU_API_KEY 配置正确 |
| 10秒超时 | Vercel 免费层函数限制 | 检查 Supabase 响应速度，减少 top_k |
| pgvector 报错 | SQL 中 CREATE EXTENSION 未执行 | 在 SQL Editor 重新执行 `CREATE EXTENSION IF NOT EXISTS vector;` |

---

## 费用

| 服务 | 费用 |
|------|------|
| Vercel | 免费（Hobby Plan） |
| Supabase | 免费（500MB 存储、50万 API 请求/月） |
| 智谱 AI | 注册赠送 token，简历展示够用 |
| DeepSeek | 按量计费，极低成本 |
