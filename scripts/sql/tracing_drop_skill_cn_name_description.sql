# -*- coding: utf-8 -*-
-- Migration: Drop skill_cn_name and skill_description from swe_tracing_spans
-- Description: 删除 swe_tracing_spans 表的 skill_cn_name 与 skill_description
--              字段；技能展示名由 swe_skills 表按 skill_id 关联后提供。
-- Date: 2026-08-04
-- 依赖：先调用 /monitor/tracing/admin/spans/init-skill-id 完成历史
--       span 的 skill_id 回填。

SET NAMES utf8mb4;

-- ============================================================
-- Migration 1: Drop skill_cn_name column
-- ============================================================
ALTER TABLE `swe_tracing_spans`
DROP COLUMN `skill_cn_name`;

-- ============================================================
-- Migration 2: Drop skill_description column
-- ============================================================
ALTER TABLE `swe_tracing_spans`
DROP COLUMN `skill_description`;

-- ============================================================
-- Verification
-- ============================================================
SHOW FULL COLUMNS FROM `swe_tracing_spans`
WHERE Field IN ('skill_cn_name', 'skill_description');
