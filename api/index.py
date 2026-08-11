"""
前事鉴 - Vercel Serverless Backend (RAG 版)
使用智谱 AI Embedding API + Supabase pgvector 实现完整 RAG
"""
import os
import json
import httpx
from datetime import datetime, date
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="前事鉴 API (RAG)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ 配置 ============
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
ZHIPU_BASE_URL = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "embedding-3")

# ============ Supabase 客户端辅助 ============
def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

async def supabase_request(method: str, path: str, body=None, params=None):
    """发送请求到 Supabase REST API"""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=supabase_headers(), json=body, params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=f"Supabase error: {resp.text}")
        if resp.status_code == 204:
            return []
        return resp.json()

async def supabase_rpc(fn_name: str, body: dict):
    """调用 Supabase RPC函数"""
    url = f"{SUPABASE_URL}/rest/v1/rpc/{fn_name}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=supabase_headers(), json=body)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=f"Supabase RPC error: {resp.text}")
        return resp.json()

# ============ Embedding API ============
async def get_embedding(text: str) -> List[float]:
    """调用智谱 AI Embedding API 获取文本向量（embedding-3, 2048维）"""
    if not ZHIPU_API_KEY:
        raise HTTPException(status_code=500, detail="ZHIPU_API_KEY not configured")
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{ZHIPU_BASE_URL}/embeddings",
            headers={
                "Authorization": f"Bearer {ZHIPU_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": text,
            }
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Embedding API error: {resp.text}")
        data = resp.json()
        return data["data"][0]["embedding"]

# ============ DeepSeek LLM ============
async def call_deepseek(system_prompt: str, user_prompt: str) -> str:
    """调用 DeepSeek Chat API"""
    if not DEEPSEEK_API_KEY:
        return "（未配置 DeepSeek API Key，无法生成 AI 分析）"
    
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 1500,
            }
        )
        if resp.status_code != 200:
            return f"（DeepSeek API 调用失败: {resp.status_code}）"
        data = resp.json()
        return data["choices"][0]["message"]["content"]

# ============ 数据模型 ============
class RecordCreate(BaseModel):
    # 兼容前端 v5 格式（today_events/tomorrow_plan/date）
    today_events: Optional[str] = ""
    tomorrow_plan: Optional[str] = ""
    date: Optional[str] = None
    # 也兼容新格式（scene/handling/result/record_date）
    scene: Optional[str] = ""
    handling: Optional[str] = ""
    result: Optional[str] = ""
    reflection: Optional[str] = ""
    record_date: Optional[str] = None

class ExperienceCreate(BaseModel):
    title: str
    content: str
    category: Optional[str] = ""
    tags: Optional[str] = ""

class SearchQuery(BaseModel):
    query: str
    top_k: Optional[int] = 5

# ============ API 路由 ============

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "vercel-rag-v1",
        "rag_enabled": bool(ZHIPU_API_KEY and SUPABASE_URL),
        "llm_enabled": bool(DEEPSEEK_API_KEY),
    }

# ---------- 每日记录 ----------
@app.post("/api/records")
async def save_record(record: RecordCreate):
    """保存每日记录，兼容前端 v5 格式和新格式"""
    # 字段适配：前端发 today_events/tomorrow_plan/date，数据库存 scene/handling/result/record_date
    scene = record.scene or record.today_events or ""
    handling = record.handling or ""
    result_text = record.result or ""
    reflection = record.reflection or record.tomorrow_plan or ""
    record_date = record.record_date or record.date or date.today().isoformat()
    
    data = {
        "scene": scene,
        "handling": handling,
        "result": result_text,
        "reflection": reflection,
        "record_date": record_date,
        "created_at": datetime.now().isoformat(),
    }
    
    result = await supabase_request("POST", "daily_records", body=data)
    record_id = result[0]["id"] if result else None
    
    # 同步提炼经验（Serverless 限制）
    extract_result = None
    if DEEPSEEK_API_KEY and scene:
        system_prompt = """你是一位职场经验提炼专家。根据用户的工作记录，提炼出可复用的经验教训。
输出JSON格式：{"title": "经验标题", "content": "详细经验内容", "category": "分类", "tags": "标签1,标签2"}
分类只能从以下选取：沟通协作、技术决策、项目管理、职场人际、自我管理"""
        
        user_prompt = f"今日记录：{scene}\n明日计划：{reflection}"
        if handling:
            user_prompt = f"场景：{scene}\n处理方式：{handling}\n结果：{result_text}\n反思：{reflection}"
        
        try:
            ai_response = await call_deepseek(system_prompt, user_prompt)
            # 尝试解析 JSON
            ai_response_clean = ai_response.strip()
            if ai_response_clean.startswith("```"):
                ai_response_clean = ai_response_clean.split("\n", 1)[1].rsplit("```", 1)[0]
            extract_result = json.loads(ai_response_clean)
        except (json.JSONDecodeError, Exception):
            extract_result = None
    
    return {
        "success": True,
        "id": record_id,
        "record": {"id": record_id, "record_date": record_date},
        "extract_candidate": extract_result,
    }

@app.get("/api/records")
async def get_records(year: Optional[int] = None, month: Optional[int] = None):
    """获取记录列表"""
    params = {"select": "*", "order": "record_date.desc"}
    
    if year and month:
        start = f"{year}-{month:02d}-01"
        if month == 12:
            end = f"{year + 1}-01-01"
        else:
            end = f"{year}-{month + 1:02d}-01"
        params["record_date"] = f"gte.{start}"
        params["record_date"] = f"lt.{end}"
        # Supabase REST API 多条件需要用 and 语法
        path = f"daily_records?select=*&order=record_date.desc&record_date=gte.{start}&record_date=lt.{end}"
        result = await supabase_request("GET", path)
    else:
        result = await supabase_request("GET", "daily_records", params=params)
    
    return {"records": result}

# ---------- 经验库 ----------
@app.get("/api/experiences")
async def get_experiences(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    category: Optional[str] = None,
):
    """获取经验列表（关键词过滤）"""
    # 构建查询
    path = f"experiences?select=*&order=created_at.desc"
    
    if keyword:
        path += f"&or=(title.ilike.%25{keyword}%25,content.ilike.%25{keyword}%25)"
    if category:
        path += f"&category=eq.{category}"
    
    # 分页
    offset = (page - 1) * page_size
    path += f"&limit={page_size}&offset={offset}"
    
    result = await supabase_request("GET", path)
    
    # 获取总数
    count_path = "experiences?select=id"
    if keyword:
        count_path += f"&or=(title.ilike.%25{keyword}%25,content.ilike.%25{keyword}%25)"
    if category:
        count_path += f"&category=eq.{category}"
    count_result = await supabase_request("GET", count_path)
    total = len(count_result)
    
    return {
        "experiences": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@app.post("/api/experiences")
async def create_experience(exp: ExperienceCreate):
    """创建经验（同时生成向量）"""
    data = {
        "title": exp.title,
        "content": exp.content,
        "category": exp.category or "",
        "tags": exp.tags or "",
        "created_at": datetime.now().isoformat(),
    }
    
    # 生成 Embedding 向量
    if ZHIPU_API_KEY:
        try:
            text_for_embedding = f"{exp.title} {exp.content}"
            embedding = await get_embedding(text_for_embedding)
            data["embedding"] = embedding
        except Exception as e:
            print(f"Embedding generation failed: {e}")
            # 向量生成失败不阻塞保存
    
    result = await supabase_request("POST", "experiences", body=data)
    return {"success": True, "experience": result[0] if result else None}

@app.put("/api/experiences/{exp_id}")
async def update_experience(exp_id: int, exp: ExperienceCreate):
    """更新经验"""
    data = {
        "title": exp.title,
        "content": exp.content,
        "category": exp.category or "",
        "tags": exp.tags or "",
    }
    
    # 重新生成向量
    if ZHIPU_API_KEY:
        try:
            text_for_embedding = f"{exp.title} {exp.content}"
            embedding = await get_embedding(text_for_embedding)
            data["embedding"] = embedding
        except Exception:
            pass
    
    result = await supabase_request("PATCH", f"experiences?id=eq.{exp_id}", body=data)
    return {"success": True, "experience": result[0] if result else None}

@app.delete("/api/experiences/{exp_id}")
async def delete_experience(exp_id: int):
    """删除经验"""
    await supabase_request("DELETE", f"experiences?id=eq.{exp_id}")
    return {"success": True}

# ---------- RAG 语义搜索 ----------
@app.post("/api/search")
async def rag_search(query: SearchQuery):
    """
    RAG 语义搜索：
    1. 用SiliconFlow Embedding 把查询转成向量
    2. 在 Supabase pgvector 中做相似度检索
    3. 把检索结果喂给 DeepSeek 生成综合建议
    """
    if not ZHIPU_API_KEY:
        raise HTTPException(status_code=500, detail="未配置智谱 AI API Key，无法使用语义搜索")
    
    # Step 1: 生成查询向量
    query_embedding = await get_embedding(query.query)
    
    # Step 2: 调用 Supabase RPC 函数做向量相似度搜索
    match_result = await supabase_rpc("match_experiences", {
        "query_embedding": query_embedding,
        "match_threshold": 0.3,
        "match_count": query.top_k,
    })
    
    if not match_result:
        return {
            "answer": "未找到相关经验记录。试试换个说法搜索？",
            "sources": [],
        }
    
    # Step 3: 用检索结果 + DeepSeek 生成综合建议
    context_parts = []
    sources = []
    for i, item in enumerate(match_result, 1):
        context_parts.append(f"[经验{i}] {item['title']}\n{item['content']}")
        sources.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "content": item.get("content", "")[:200],
            "category": item.get("category", ""),
            "similarity": item.get("similarity", 0),
        })
    
    context_text = "\n\n".join(context_parts)
    
    if DEEPSEEK_API_KEY:
        system_prompt = """你是一位资深职场顾问。根据用户的问题和检索到的相关经验，给出实用的建议。
要求：
1. 综合多条经验给出建议，不要简单复述
2. 结合具体场景给出可操作的行动建议
3. 如果经验之间有冲突，指出不同情况下的最佳选择
4. 语言简洁有力，避免空话"""
        
        user_prompt = f"我的问题：{query.query}\n\n相关经验：\n{context_text}"
        answer = await call_deepseek(system_prompt, user_prompt)
    else:
        answer = "（未配置 DeepSeek API Key。以下是语义匹配到的相关经验：）\n\n" + context_text
    
    return {
        "answer": answer,
        "sources": sources,
    }

# ---------- 记录分析（保存后触发）----------
@app.post("/api/analyze-record")
async def analyze_record(record: RecordCreate):
    """分析记录并推荐相关经验"""
    text = f"{record.scene} {record.handling} {record.result}"
    
    result = {"type": "none", "message": ""}
    
    if ZHIPU_API_KEY:
        try:
            embedding = await get_embedding(text)
            matches = await supabase_rpc("match_experiences", {
                "query_embedding": embedding,
                "match_threshold": 0.5,
                "match_count": 3,
            })
            if matches:
                result = {
                    "type": "remind",
                    "message": f"发现 {len(matches)} 条相关经验",
                    "related": [{"title": m["title"], "id": m["id"]} for m in matches],
                }
        except Exception:
            pass
    
    return result

# ---------- 智能提醒（输入时实时匹配）----------
class ReminderRequest(BaseModel):
    content: str
    scene: Optional[str] = ""

@app.post("/api/reminder")
async def smart_reminder(req: ReminderRequest):
    """根据用户正在输入的内容，实时匹配相关经验并生成提醒"""
    text = req.content.strip()
    if not text or len(text) < 4:
        return {"matched": False}
    
    if not ZHIPU_API_KEY:
        return {"matched": False}
    
    try:
        embedding = await get_embedding(text)
        matches = await supabase_rpc("match_experiences", {
            "query_embedding": embedding,
            "match_threshold": 0.5,
            "match_count": 3,
        })
        if not matches:
            return {"matched": False}
        
        # 构建提醒文案
        exp_titles = [m["title"] for m in matches[:3]]
        reminder_text = f"你之前记录过相关经验：{'、'.join(exp_titles)}。可以参考一下。"
        
        # 如果有 DeepSeek，生成更智能的提醒
        if DEEPSEEK_API_KEY and len(matches) > 0:
            context = "\n".join([f"- {m['title']}: {m.get('content','')[:100]}" for m in matches[:3]])
            system_prompt = "你是职场经验助手。用户正在记录工作，你需要根据匹配到的历史经验，用一两句话给出简短实用的提醒。不要重复经验原文，只给出关键提醒。"
            user_prompt = f"用户正在写：{text}\n\n匹配到的经验：\n{context}"
            try:
                reminder_text = await call_deepseek(system_prompt, user_prompt)
            except Exception:
                pass
        
        return {
            "matched": True,
            "reminder": reminder_text,
            "experiences": [{"id": m.get("id"), "title": m["title"]} for m in matches[:3]],
        }
    except Exception:
        return {"matched": False}

@app.post("/api/reminder/feedback")
async def reminder_feedback(data: dict):
    """记录智能提醒反馈（简单记录，后续可用于优化）"""
    # 目前只返回成功，后续可存入 Supabase
    return {"success": True}

# ============ Vercel 入口 ============
# Vercel Python Runtime 自动检测 app变量
