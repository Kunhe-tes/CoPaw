-- ============================================================
-- Tracing Skill Description Migration
-- Date: 2026-05-21
-- Description: 添加 skill_description 列到 swe_tracing_spans 表
-- ============================================================

SET NAMES utf8mb4;

-- 添加 skill_description 列
ALTER TABLE `swe_tracing_spans`
ADD COLUMN `skill_description` TEXT DEFAULT NULL COMMENT '技能描述，从 SKILL.md 的 description 字段读取'
AFTER `skill_name`;

SET FOREIGN_KEY_CHECKS = 1;