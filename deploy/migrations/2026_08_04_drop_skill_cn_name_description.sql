-- 技能追踪字段调整：移除 swe_tracing_spans 中的 skill_cn_name 与
-- skill_description 字段。技能展示名改由 swe_skills 表按 skill_id
-- 关联后提供；技能描述由前端按需从 swe_skills.description 读取。
-- 本迁移必须在完成历史 skill_id 回填后再执行。

-- ============================================================
-- Migration 1: 删除 skill_cn_name
-- ============================================================
ALTER TABLE `swe_tracing_spans`
DROP COLUMN `skill_cn_name`;

-- ============================================================
-- Migration 2: 删除 skill_description
-- ============================================================
ALTER TABLE `swe_tracing_spans`
DROP COLUMN `skill_description`;

-- ============================================================
-- Verification
-- ============================================================
SHOW FULL COLUMNS FROM `swe_tracing_spans`
WHERE Field IN ('skill_cn_name', 'skill_description');
