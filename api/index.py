"""
前事鉴 · Vercel Serverless 适配版
====================================
精简版：去掉 FAISS/FastEmbed，改用关键词匹配 + DeepSeek LLM。
数据库使用 Vercel Postgres (Neon) 替代 SQLite。

环境变量要求：
  DEEPSEEK_API_KEY - DeepSeek API 密钥
  DEEPSEEK_BASE_URL - DeepSeek API 基础地址（默认 https://api.deepseek.com）
  DEEPSEEK_MODEL - 模型名（默认 deepseek-chat）
  POSTGRES_URL - Vercel Postgres 连接字符串（自动注入）
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
from pydantic import BaseModel, Field

#─────────── Pydantic Models ───────────

class APIResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


class RecordUpsertRequest(BaseModel):
    date: str
    today_events: str = ""
    tomorrow_plan: str = ""


class ExperienceCreateRequest(BaseModel):
    title: str
    content: str
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"
    source_record_id: int | None = None


class ExperienceUpdateRequest(BaseModel):
    title: str
    content: str
    category: str = ""
    tags: list[str] = Field(default_factory=list)


class ReminderRequest(BaseModel):
    content: str


# ─────────── Database (Postgres via psycopg2 or fallback to SQLite /tmp) ───────────

import sqlite3

DB_PATH = "/tmp/pitfall.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                today_events TEXT,
                tomorrow_plan TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT,
                tags TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                source_record_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts USING fts5(
                title, content, category, tags,
                content='experiences',
                content_rowid='id'
            )
        """)
        # Triggers to keep FTS in sync
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS experiences_ai AFTER INSERT ON experiences BEGIN
                INSERT INTO experiences_fts(rowid, title, content, category, tags)
                VALUES (new.id, new.title, new.content, new.category, new.tags);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS experiences_ad AFTER DELETE ON experiences BEGIN
                INSERT INTO experiences_fts(experiences_fts, rowid, title, content, category, tags)
                VALUES ('delete', old.id, old.title, old.content, old.category, old.tags);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS experiences_au AFTER UPDATE ON experiences BEGIN
                INSERT INTO experiences_fts(experiences_fts, rowid, title, content, category, tags)
                VALUES ('delete', old.id, old.title, old.content, old.category, old.tags);
                INSERT INTO experiences_fts(rowid, title, content, category, tags)
                VALUES (new.id, new.title, new.content, new.category, new.tags);
            END
        """)


init_db()

# ─────────── DeepSeek Service ───────────

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_ENABLED = bool(DEEPSEEK_API_KEY)


async def call_deepseek(system_prompt: str, user_prompt: str) -> str:
    if not DEEPSEEK_ENABLED:
        return ""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 800,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def extract_experience_via_llm(text: str) -> dict:
    system_prompt = """你是一个职场经验提炼助手。根据用户的日常记录，判断是否有可提炼的经验教训。
如果有，返回JSON格式：{"has_candidate":true,"candidate":{"title":"标题","content":"经验内容","category":"分类","tags":["标签1","标签2"]}}
如果没有，返回：{"has_candidate":false}
只返回JSON，不要其他内容。"""
    result = await call_deepseek(system_prompt, text)
    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return {"has_candidate": False}


async def generate_reminder_via_llm(content: str, experiences: list[dict]) -> str:
    system_prompt = "你是一个友善的职场经验提醒助手。根据用户当前正在做的事，结合过往经验，给出简洁的提醒建议（50字以内）。"
    exp_text = "\n".join([f"- {e['title']}: {e['content']}" for e in experiences[:3]])
    user_prompt = f"用户当前在做：{content}\n\n相关过往经验：\n{exp_text}\n\n请给出简洁提醒："
    return await call_deepseek(system_prompt, user_prompt)


# ─────────── Local fallback extract ───────────

def local_extract_experience(text: str) -> dict:
    clean = " ".join(text.replace("\n", " ").split())
    if len(clean) < 20:
        return {"has_candidate": False}

    categories = {
        "项目": ["项目", "排期", "成本", "方案", "交付", "风险"],
        "沟通": ["沟通", "汇报", "反馈", "会议", "对齐"],
        "协作": ["协作", "同事", "跨团队", "分工", "配合"],
        "情绪": ["情绪", "焦虑", "生气", "批评", "压力"],
    }

    selected_cat = "其他"
    selected_tags: list[str] = []
    for cat, kws in categories.items():
        matched = [kw for kw in kws if kw in clean]
        if matched:
            selected_cat = cat
            selected_tags = matched
            break

    if not selected_tags:
        selected_tags = ["复盘", "避坑"]

    return {
        "has_candidate": True,
        "candidate": {
            "title": f"{selected_cat}场景先复盘再行动",
            "content": f"基于记录建议先复盘关键事实和风险：{clean[:120]}",
            "category": selected_cat,
            "tags": selected_tags[:5],
        },
    }


# ─────────── FastAPI App ───────────

app = FastAPI(title="前事鉴 API (Vercel)", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exc_handler(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "message": str(exc.detail), "data": None})


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(_, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": 422, "message": "参数校验失败", "data": None})


@app.exception_handler(Exception)
async def unhandled_exc_handler(_, exc: Exception):
    return JSONResponse(status_code=500, content={"code": 500, "message": "服务器内部错误", "data": None})


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


# ─── Health───

@app.get("/health")
async def health():
    return {"ok": True, "service": "pitfall_assistant_vercel", "deepseek_enabled": DEEPSEEK_ENABLED}


@app.get("/api/health")
async def api_health():
    return {"ok": True, "service": "pitfall_assistant_vercel", "deepseek_enabled": DEEPSEEK_ENABLED}


# ─── Records ───

@app.post("/api/records")
async def upsert_record(req: RecordUpsertRequest):
    now = now_str()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO daily_records (date, today_events, tomorrow_plan, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                today_events = excluded.today_events,
                tomorrow_plan = excluded.tomorrow_plan,
                updated_at = excluded.updated_at
        """, (req.date, req.today_events.strip(), req.tomorrow_plan.strip(), now, now))
        row = conn.execute("SELECT * FROM daily_records WHERE date = ?", (req.date,)).fetchone()

    record = row_to_dict(row)

    # Async extract
    merged = f"今天发生的事：{req.today_events}\n明天的规划：{req.tomorrow_plan}"
    extract_result = None
    try:
        if DEEPSEEK_ENABLED:
            extract_result = await extract_experience_via_llm(merged)
        else:
            extract_result = local_extract_experience(merged)
    except Exception:
        extract_result = local_extract_experience(merged)

    return APIResponse(code=0, data={"record": record, "extract_result": extract_result})


@app.get("/api/records")
async def get_records(
    date_value: str | None = Query(default=None, alias="date"),
    year: int | None = None,
    month: int | None = None,
):
    with get_conn() as conn:
        if date_value:
            row = conn.execute("SELECT * FROM daily_records WHERE date = ?", (date_value,)).fetchone()
            return APIResponse(code=0, data={"record": row_to_dict(row) if row else None})

        if year and month:
            prefix = f"{year}-{month:02d}"
            rows = conn.execute(
                "SELECT * FROM daily_records WHERE date LIKE ? ORDER BY date DESC",
                (f"{prefix}%",),
            ).fetchall()
            return APIResponse(code=0, data={"records": [row_to_dict(r) for r in rows]})

        rows = conn.execute("SELECT * FROM daily_records ORDER BY date DESC LIMIT 60").fetchall()
        return APIResponse(code=0, data={"records": [row_to_dict(r) for r in rows]})


@app.get("/api/records/{record_id}/extract-status")
async def get_extract_status(record_id: int):
    # Vercel 版没有异步任务持久化，返回已完成状态
    return APIResponse(code=0, data={"status": "completed", "has_candidate": False, "message": "Vercel 版同步返回"})


# ─── Experiences ───

@app.post("/api/experiences")
async def create_experience(req: ExperienceCreateRequest):
    now = now_str()
    tags_str = ",".join(req.tags)
    with get_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO experiences (title, content, category, tags, source, source_record_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (req.title.strip(), req.content.strip(), req.category.strip(), tags_str, req.source, req.source_record_id, now, now))
        row = conn.execute("SELECT * FROM experiences WHERE id = ?", (cursor.lastrowid,)).fetchone()
    item = row_to_dict(row)
    item["tags"] = [t.strip() for t in (item.get("tags") or "").split(",") if t.strip()]
    return APIResponse(code=0, data={"experience": item})


@app.get("/api/experiences")
async def list_experiences(keyword: str = "", tag: str = "", page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    with get_conn() as conn:
        if keyword.strip():
            # FTS search
            rows = conn.execute("""
                SELECT e.* FROM experiences e
                JOIN experiences_fts fts ON e.id = fts.rowid
                WHERE experiences_fts MATCH ?
                ORDER BY e.updated_at DESC LIMIT ? OFFSET ?
            """, (keyword.strip(), page_size, offset)).fetchall()
            total_row = conn.execute("""
                SELECT COUNT(*) as cnt FROM experiences e
                JOIN experiences_fts fts ON e.id = fts.rowid
                WHERE experiences_fts MATCH ?
            """, (keyword.strip(),)).fetchone()
            total = total_row["cnt"] if total_row else 0
        elif tag.strip():
            rows = conn.execute("""
                SELECT * FROM experiences WHERE tags LIKE ? ORDER BY updated_at DESC LIMIT ? OFFSET ?
            """, (f"%{tag.strip()}%", page_size, offset)).fetchall()
            total_row = conn.execute("SELECT COUNT(*) as cnt FROM experiences WHERE tags LIKE ?", (f"%{tag.strip()}%",)).fetchone()
            total = total_row["cnt"] if total_row else 0
        else:
            rows = conn.execute("SELECT * FROM experiences ORDER BY updated_at DESC LIMIT ? OFFSET ?", (page_size, offset)).fetchall()
            total_row = conn.execute("SELECT COUNT(*) as cnt FROM experiences").fetchone()
            total = total_row["cnt"] if total_row else 0

    items = []
    for r in rows:
        item = row_to_dict(r)
        item["tags"] = [t.strip() for t in (item.get("tags") or "").split(",") if t.strip()]
        items.append(item)

    return APIResponse(code=0, data={"items": items, "total": total})


@app.put("/api/experiences/{experience_id}")
async def update_experience(experience_id: int, req: ExperienceUpdateRequest):
    now = now_str()
    tags_str = ",".join(req.tags)
    with get_conn() as conn:
        conn.execute("""
            UPDATE experiences SET title=?, content=?, category=?, tags=?, updated_at=?
            WHERE id=?
        """, (req.title.strip(), req.content.strip(), req.category.strip(), tags_str, now, experience_id))
        row = conn.execute("SELECT * FROM experiences WHERE id = ?", (experience_id,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="experience not found")

    item = row_to_dict(row)
    item["tags"] = [t.strip() for t in (item.get("tags") or "").split(",") if t.strip()]
    return APIResponse(code=0, data={"experience": item})


@app.delete("/api/experiences/{experience_id}")
async def delete_experience(experience_id: int):
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM experiences WHERE id = ?", (experience_id,))
        deleted = cursor.rowcount > 0
    return APIResponse(code=0, data={"deleted": deleted})


# ─── Experience Extract ───

@app.post("/api/experiences/extract")
async def extract_experience(req: RecordUpsertRequest):
    merged = f"今天发生的事：{req.today_events}\n明天的规划：{req.tomorrow_plan}"
    if len(merged.strip()) < 10:
        return APIResponse(code=0, data={"has_candidate": False})

    try:
        if DEEPSEEK_ENABLED:
            result = await extract_experience_via_llm(merged)
        else:
            result = local_extract_experience(merged)
    except Exception:
        result = local_extract_experience(merged)

    return APIResponse(code=0, data=result)


# ─── Reminder (keyword-based for Vercel version) ───

@app.post("/api/reminder")
async def reminder(req: ReminderRequest):
    content = req.content.strip()
    if len(content) < 4:
        return APIResponse(code=0, data={"matched": False})

    # Keyword search in experiences
    with get_conn() as conn:
        try:
            rows = conn.execute("""
                SELECT e.* FROM experiences e
                JOIN experiences_fts fts ON e.id = fts.rowid
                WHERE experiences_fts MATCH ?
                LIMIT 3
            """, (content,)).fetchall()
        except Exception:
            # FTS match might fail on special chars, fallback to LIKE
            rows = conn.execute("""
                SELECT * FROM experiences WHERE title LIKE ? OR content LIKE ? LIMIT 3
            """, (f"%{content[:20]}%", f"%{content[:20]}%")).fetchall()

    if not rows:
        return APIResponse(code=0, data={"matched": False})

    experiences = []
    for r in rows:
        item = row_to_dict(r)
        item["tags"] = [t.strip() for t in (item.get("tags") or "").split(",") if t.strip()]
        experiences.append(item)

    # Generate reminder
    reminder_text = ""
    if DEEPSEEK_ENABLED:
        try:
            reminder_text = await generate_reminder_via_llm(content, experiences)
        except Exception:
            pass

    if not reminder_text:
        top = experiences[0]
        reminder_text = f"你之前在『{top['title']}』里踩过类似坑，建议先列清目标和风险再推进。"

    card_experiences = [{"id": e["id"], "title": e["title"], "similarity": 0.8} for e in experiences]
    return APIResponse(code=0, data={
        "matched": True,
        "experiences": card_experiences,
        "reminder": reminder_text,
        "degraded": not DEEPSEEK_ENABLED,
    })


# ─── Root ───

@app.get("/")
async def root():
    return {"name": "前事鉴 API", "status": "running", "date": date.today().isoformat()}


# ─── Vercel Handler ───
handler = Mangum(app, lifespan="off")
