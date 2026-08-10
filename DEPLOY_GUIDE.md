# 前事鉴 Vercel 部署指南（RAG 完整版）

>技术栈：FastAPI Serverless + SiliconFlow Embedding + Supabase pgvector + DeepSeek LLM

---

## 你需要准备的账号/API Key

| 服务 | 作用 | 注册地址 | 费用 |
|------|------|---------|------|
| **Vercel** | 应用托管 | https://vercel.com | 免费 |
| **Supabase** | 数据库 + 向量存储 | https://supabase.com | 免费（500MB） |
| **硅基流动 SiliconFlow** | 文本转向量（Embedding） | https://cloud.siliconflow.cn | 免费额度充足 |
| **DeepSeek** | LLM 经验提炼 + RAG 生成回答 | https://platform.deepseek.com | 按量付费，极低 |

---

## 第一步：配置 Supabase 数据库

1. 注册 [supabase.com](https://supabase.com) 并登录
2. 点击 **New Project** → 设置：
   - Name: `pitfall-assistant`
   - Database Password: 记住这个密码
   - Region: 选 `Northeast Asia (Tokyo)` 或 `Southeast Asia (Singapore)`
3. 等待项目创建完成（约 1 分钟）
4. 进入项目 → 左侧菜单点**SQL Editor**
5. 把`supabase_init.sql` 的全部内容粘贴进去 → 点 **Run**
6. 进入 **Settings → API**，复制：
   - `Project URL`（如 `https://xxxxx.supabase.co`）
   - `anon public` Key（以 `eyJ` 开头的长字符串）

---

## 第二步：获取 SiliconFlow API Key

1. 注册 [cloud.siliconflow.cn](https://cloud.siliconflow.cn)
2. 进入控制台 → **API 密钥** → **新建 API 密钥**
3. 复制生成的 Key（以 `sk-` 开头）

---

## 第三步：获取 DeepSeek API Key

1. 注册 [platform.deepseek.com](https://platform.deepseek.com)
2. 进入控制台 → **API Keys** → **Create new key**
3. 复制生成的 Key

---

## 第四步：推代码到 GitHub

```bash
cd app_vercel
git add .
git commit -m "feat: RAG version with SiliconFlow + Supabase pgvector"
git push
```

---

## 第五步：在 Vercel 配置环境变量

1. 打开 [Vercel Dashboard](https://vercel.com) → 你的项目
2. 进入 **Settings → Environment Variables**
3. 添加以下变量：

```
DEEPSEEK_API_KEY=sk-你的deepseek密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
SUPABASE_URL=https://你的项目.supabase.co
SUPABASE_KEY=eyJ你的anon_key...
SILICONFLOW_API_KEY=sk-你的硅基流动密钥
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
```

4. 点Save 保存

---

## 第六步：重新部署

环境变量修改后需要重新部署：
-进入 **Deployments** → 点最新一条→ **⋮** → **Redeploy**
- 或者推一次新commit，Vercel 会自动重新部署

---

## 完成 ✅

访问你的 Vercel 地址（如 `https://lessons-assistant.vercel.app`），即可：

1. **记录经验** → 保存后自动调DeepSeek 提炼
2. **确认经验** → 存入 Supabase +生成向量
3. **语义搜索** → 向量检索 + LLM 生成建议（完整RAG）

---

## 项目架构

```
用户输入 → Vercel Serverless Function (FastAPI)
                ├── 保存记录 → Supabase (PostgreSQL)
                ├── 经验提炼 → DeepSeek Chat API
                ├── 生成向量 → SiliconFlow Embedding API → Supabase pgvector
                └── 语义搜索 → SiliconFlow 生成查询向量
                → Supabase pgvector 相似度检索
                              → DeepSeek 生成综合建议
```

---

## 常见问题

| 问题 | 解决 |
|------|------|
| 搜索返回空| 确认经验库有数据且向量已生成 |
| "Embedding API error" | 检查 SILICONFLOW_API_KEY 是否正确 |
| "Supabase error" | 检查 SUPABASE_URL/KEY，确认SQL 已执行 |
| 保存成功但无提炼 | 检查 DEEPSEEK_API_KEY |
| 函数超时 | Vercel 免费层限 10s，如果 DeepSeek 响应慢可能触发 |

---

## 简历写法建议

```
前事鉴 — 职场经验管理与RAG 智能检索系统
技术栈：FastAPI + Supabase pgvector + SiliconFlow Embedding + DeepSeek LLM
核心：向量语义检索（bge-m3）+ 检索增强生成（RAG）+ LLM 经验自动提炼
部署：Vercel Serverless，零运维
演示：https://lessons-assistant.vercel.app
源码：https://github.com/xxx/lessons-assistant
```
