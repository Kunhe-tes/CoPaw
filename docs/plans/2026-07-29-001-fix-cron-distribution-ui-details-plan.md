---
title: "fix: Refine scheduled firing distribution interactions and details"
type: fix
status: completed
date: 2026-07-29
origin: screenshots supplied in the 2026-07-29 Codex task
---

# fix: Refine scheduled firing distribution interactions and details

## Problem Frame

The scheduled firing distribution page exposes useful density data, but several
presentation details make it harder to scan: Text and Agent KPI labels are too
generic, invalid-Cron diagnostics add unwanted visual noise, chart hover dims an
entire series instead of isolating one time bucket, the ranked bucket list cannot
show more than eight entries, and the detail drawer does not identify the owning
user account.

## Requirements

- R1. Label KPI cards as `Text型任务` and `Agent型任务`.
- R2. Do not render the `无效 Cron` diagnostic in this page.
- R3. Hovering a chart bucket highlights only that bucket's Text and Agent bars.
- R4. Show all non-empty ranked buckets inside an independently scrollable list.
- R5. Detail rows show one `用户/账号` column containing user name and account ID.
- R6. Preserve the existing eligibility rule: only enabled, active, non-deleted
  Scheduled Jobs participate in aggregate and detail results.

## Scope Boundaries

- Keep the aggregate algorithm, bucket definitions, Text/Agent classification,
  pagination, and source isolation unchanged.
- Add only whitelisted account identity fields to the detail DTO; do not expose
  task content, session data, or broad Cron job records.
- Do not change database schema or persistence.
- Do not modify unrelated W+ workspace changes already present in the worktree.

## Key Decisions

- Use `swe_cron_jobs.tenant_name` as the display name and `tenant_id` as the
  account ID, matching existing Monitor management views that alias these fields
  to `user_name` and `user_id`.
- Include both identity fields in the detail definition revision because a name
  or account change affects paginated row content.
- Keep invalid-Cron counts in the backend response for diagnostics; suppress only
  this page's visual rendering.

## Implementation Units

### U1. Extend the detail contract with account identity

**Goal:** Return a bounded user name and account ID with each planned firing row.

**Requirements:** R5, R6

**Dependencies:** None

**Files:**
- Modify: `monitor/src/monitor/app/models/cron.py`
- Modify: `monitor/src/monitor/app/services/cron/query_service.py`
- Test: `monitor/tests/test_cron_schedule_distribution.py`

**Approach:**
- Select tenant identity with the existing active-definition query.
- Carry it through prepared definitions and materialized detail occurrences.
- Add `user_name` and `user_id` to the dedicated detail response item and
  definition revision; do not add them to aggregate buckets.

**Execution note:** Start with failing response-contract and revision tests.

**Test scenarios:**
- A valid active job returns its tenant name and ID in every generated detail row.
- Disabled, paused, and deleted jobs remain excluded from both counts and details.
- Changing only the account name changes the definition revision used by detail
  pagination.

**Verification:** Targeted Monitor distribution tests and route/OpenAPI contract
tests pass.

### U2. Refine dashboard interactions and presentation

**Goal:** Match the annotated page behavior without changing query semantics.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** U1

**Files:**
- Modify: `console/src/api/modules/monitor.ts`
- Modify: `console/src/pages/Analytics/ContinuousGovernance/CronScheduleDistribution/index.tsx`
- Modify: `console/src/pages/Analytics/ContinuousGovernance/CronScheduleDistribution/index.module.less`
- Test: `console/src/pages/Analytics/ContinuousGovernance/CronScheduleDistribution/index.test.tsx`

**Approach:**
- Update labels and suppress only invalid-Cron display text.
- Remove the eight-row ranking cap and constrain the list with vertical scrolling.
- Use ECharts highlight/downplay actions so both stacked series at one data index
  are emphasized together without blurring a full series.
- Render name plus account ID in one ellipsized detail column.

**Execution note:** Add failing component assertions before implementation.

**Test scenarios:**
- KPI cards use the requested labels and invalid-Cron text is absent while other
  diagnostics can still render.
- More than eight populated buckets remain present in the ranking list.
- Chart mouseover highlights Text and Agent at the hovered data index, and
  mouseout clears the highlight.
- The detail table renders user name and account ID from the API payload.

**Verification:** Targeted Vitest coverage, TypeScript type checking, and a
browser-sized visual check pass.

## Risks

- ECharts event callbacks can accidentally create sticky emphasis; explicitly
  downplay before highlight and on mouseout.
- Adding response fields can invalidate page-two detail requests when identity
  changes; including identity in the revision makes that behavior explicit.
- A long ranked list must not expand the entire page; constrain only the list so
  chart and panel headers remain fixed.
