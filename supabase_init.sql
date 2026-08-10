-- ========================================
-- 前事鉴 Supabase 初始化 SQL（RAG 版）
-- 在 Supabase Dashboard → SQL Editor 中执行
-- ========================================

-- 1. 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 每日记录表
CREATE TABLE IF NOT EXISTS daily_records (
    id BIGSERIAL PRIMARY KEY,
    scene TEXT NOT NULL,
    handling TEXT NOT NULL,
    result TEXT NOT NULL,
    reflection TEXT DEFAULT '',
    record_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 经验库表（含向量列）
CREATE TABLE IF NOT EXISTS experiences (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    embedding vector(1024),-- bge-m3 输出1024 维向量
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. 创建向量索引（IVFFlat，适合中小数据量）
CREATE INDEX IF NOT EXISTS experiences_embedding_idx 
ON experiences 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 10);

-- 5. 向量相似度搜索函数
CREATE OR REPLACE FUNCTION match_experiences(
    query_embedding vector(1024),
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id BIGINT,
    title TEXT,
    content TEXT,
    category TEXT,
    tags TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id,
        e.title,
        e.content,
        e.category,
        e.tags,
        1- (e.embedding <=> query_embedding) AS similarity
    FROM experiences e
    WHERE e.embedding IS NOT NULL
    AND1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 6. 启用 Row Level Security（可选，安全加固）
-- ALTER TABLE daily_records ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE experiences ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow all" ON daily_records FOR ALL USING (true);
-- CREATE POLICY "Allow all" ON experiences FOR ALL USING (true);
