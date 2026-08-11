-- 修复 daily_records 表：允许 handling 和 result 为空字符串
-- 在 Supabase SQL Editor 中执行

ALTER TABLE daily_records ALTER COLUMN scene SET DEFAULT '';
ALTER TABLE daily_records ALTER COLUMN handling SET DEFAULT '';
ALTER TABLE daily_records ALTER COLUMN result SET DEFAULT '';

-- 去掉 NOT NULL 约束（如果有的话），改为允许空字符串
ALTER TABLE daily_records ALTER COLUMN handling DROP NOT NULL;
ALTER TABLE daily_records ALTER COLUMN result DROP NOT NULL;
