---
name: wplus-sop-miner
description: 将模糊的业务、客户筛选或分析需求，通过环节拆分、逐环节澄清、逐环节预跑和反馈闭环，整理为用户确认的结构化 SOP。优先用于招商银行财富 W+ 的客户列表筛选、资产变化排查、产品到期、收益分析和跟进流程；当用户正在澄清一个具体工作流程且没有更合适的现有技能承载时，将本技能作为 SOP 澄清兜底。
---

# W+ SOP 挖掘技能

把用户实际采用的工作流程澄清为可验证的 SOP，不替用户发明标准流程。默认使用中文与用户交互。

## 严守边界

- 以用户本轮明确说法为最高优先级事实；平台资料、能力注册表和记忆只作为提问线索。
- 不推断未记录的字段、阈值、权限、数据口径或业务规则。
- 澄清期间不提前调用 W+、OpenCLI、MCP 或其他真实数据源。进入预跑后，
  由 CoPaw 后端 Agent 和受控工具运行时使用已确认输入替用户执行当前环节；
  不要求用户复制命令或自行预跑。
- 不得因为是预跑而绕过 Tool Guard、权限确认、沙箱或外部副作用审批。审批
  被拒绝、超时或权限不足时，提交结构化失败状态，不得伪装成已验证。
- 不在状态、记忆或输出中保存客户姓名、客户标识、账号、卡号、余额、自由文本备注、凭证、交易明细或原始响应。
- 只读能力不能被描述为写能力；无法承载的动作标为 `human_action` 或 `unsupported`。
- 若另一个已存在技能能完整承载当前需求，优先使用该技能；只有没有合适技能时才以通用模式运行本技能。
- OpenCLI 文档、能力注册表、平台功能图或页面索引需要新增、修订或同步时，改用 `$wplus-capability-catalog-maintainer`；本技能不得在澄清会话中修改知识目录。

## 按需读取

1. 始终先读 `references/demand-routing.md`，判断是否采用默认名单分析流程，并提出 2–4 个环节的队列。
2. W+ 模式下，在提出第一个问题前依次读取：
   - `references/memory-policy.md`；
   - `references/platform-function-map.md`；
   - 与需求相关的 `references/page-index.md`；
   - 需要提供页面或 OpenCLI 选项时，运行 `scripts/search_capabilities.py` 查询 `references/capability-registry.json`。
3. 通用兜底模式不加载 W+ 记忆、页面或能力资料，除非用户随后明确把流程落到 W+。
4. 环节队列确认后读取 `references/question-policy.md`；每个环节开始和切换时遵守 `references/stage-workflow.md`。
5. 所有环节确认后再读取 `references/output-contract.md` 和 `references/sop-schema.json`。

## CoPaw 工作台协议

- 本技能只在后端已经提供 `wplus_sop_session_id` 且
  `emit_wplus_sop_event` 可用时进入工作台流程。会话由平台在用户确认入口后
  先创建；本技能不得创建、替换或猜测会话。
- 普通 Chat（没有上述 Session/工具上下文）可以按
  `references/demand-routing.md` 用 Markdown 展示候选队列并等待用户确认；
  该 Markdown 只是对话内容，不得声称已经推进 CoPaw 工作台状态。
- CoPaw 工作台首轮不得只展示 Markdown。必须且只能调用一次
  `emit_wplus_sop_event(kind='stage_proposal', ...)`，其 `payload` 顶层为
  `stages` 数组；每项使用 `stage_id`、`name`、`description`、`status`。
  `references/state-schema.json` 中业务状态快照的 `stage_queue[].id` 仅是
  Miner 内部状态字段，提交工作台事件时必须映射为 `stages[].stage_id`，
  不得把 `id` 直接作为事件字段。
- 每个业务边界都调用 `emit_wplus_sop_event` 提交类型化事件。Markdown 仅
  用作可读摘要，不能承载按钮、题目选项、状态或恢复真源。
- 事件中的 `session_id`、`chat_id`、租户、来源、用户和 Agent 归属由平台
  上下文提供；不要从用户文本接收或覆盖这些字段。
- 同一 Agent run 重发事件时复用平台给出的稳定业务事件键。真正的失败重试
  或反馈重跑使用平台创建的新 run/attempt，并保留
  `retry_of_run_id` 或 `rerun_of_run_id`。
- 若结构化工具缺失、会话不存在、事件 schema 不合法或创建时固定的技能
  契约不可用，停止当前推进并返回可恢复失败；不得退化为解析 Markdown 或让
  用户自行执行。

## 强制状态机

第一次回应只通过 `stage_proposal` 提交 2–4 个环节的完整候选队列，不得
同时提交第一个环节的问题。用户确认或原子调整整份队列后，平台才启动下一
个 Miner 回合生成题组。

环节队列确认后，对每个环节严格执行：

```text
clarifying
→ ready_for_trial
→ trial_running
→ feedback_review
→ awaiting_stage_confirmation
→ confirmed
```

- 使用 `references/state-schema.json` 记录 `current_stage_id`、问题进度、环节状态和 `next_required_transition`。
- 当前环节未到 `confirmed` 时，不得进入下一环节。
- 用户反馈改变流程时，把反馈写回当前环节，回到 `ready_for_trial` 并重新预跑，不得带着未验证修改继续。
- 用户提交反馈时只修改当前环节，并通过 `trial_feedback_accepted` 关联前次
  run；平台创建新 run 后重新执行受影响步骤。
- 用户接受预跑结果后，先提交 `stage_confirmation_required`。只有用户在
  工作台确认当前环节无误，才提交 `stage_confirmed`。若有下一环节，在同一
  原子转换中激活下一环节，然后由新的 Miner 回合生成下一环节题组。
- 最后一个环节确认后，才进入总体检查和最终输出。

## 澄清与预跑

- 每轮只处理当前环节，提出 1–3 个最高价值问题。
- 把完整题组一次性提交为 `question_batch`，为每题和选项提供稳定 ID；不要
  在 Markdown 中制作第二套可提交控件。
- `B` 是当前问题清单总数；反馈暴露新缺口时可以调整，但必须同步更新状态并明确显示。
- 只有当前环节的入口、范围、口径、规则、输出和下一动作都已确认、明确未知或不适用时，才进入该环节预跑。
- 预跑是每个环节的必经步骤，不是所有环节完成后的可选总体验证。
- 进入预跑时先提交 `trial_plan`，冻结能力版本、输入快照、步骤与脱敏输出
  契约；随后由后端运行时执行并提交 started/progress/completed/failed 事件。
- `opencli` 环节必须记录能力名称、适配器、命令、验证状态和必要输入来源，
  并由平台使用对应 OpenCLI；不得要求用户自行执行，也不得在工具失败时声称
  已取得真实数据。
- 预跑结果只包含脱敏摘要、计数、schema 校验、警告与失败位置。原始客户
  响应不得进入事件 payload、Chat 投影或浏览器。
- 预跑完成后必须停在工作台反馈态。反馈只修改当前环节；修改后由系统重新
  预跑，直到用户明确接受结果并确认该环节。

## 能力分类

每个环节只能采用一种主分类：

- `opencli`：只读能力和输入契约明确；
- `analysis`：基于已确认输入或前序输出进行分析；
- `human_action`：由客户经理人工完成；
- `unsupported`：没有可用能力，也没有安全明确的人工交接。

把被实际引用能力的最小必要契约写入 `capability_snapshot`，保留原始 `verification_status`，不得把 `partial` 或 `unverified` 升级为已验证。

## 完成与交付

- 总体检查发现缺口时，返回缺口所属环节，重新走完该环节的澄清、预跑、反馈和确认。
- 最终 `sop_spec.json` 中所有完成环节的 `verification_mode` 必须是 `user_confirmed`，并保留脱敏的 `trial_notes`。
- 生成并验证 `sop_spec.json`、`sop_render.md`、`sop_render.html` 和基于预跑脱敏数据及模板生成的 `example_result.html`。
- 必须通过 `copy_file_to_static` 工具逐个把以上文件复制到 `static` 目录；只交付工具返回的静态路径，不得用普通文件复制代替，也不得在复制失败时声称已交付。
- 不得自动调用技能构建器；只说明已确认 SOP 可交给 `$wplus-skill-builder`。
- 三类必需结果全部通过结构和文件校验后，依次提交 `sop_result` 与
  `memory_candidates`。没有记忆候选时平台可直接完成；有候选时用户逐项
  批准或跳过后，再按 `references/memory-policy.md` 幂等写入。

## 停止条件

遇到会改变流程含义但用户无法确认的缺口、未定义口径、未记录写能力、必要输入来源不明、模板缺失或只能使用客户级敏感值时，明确说明阻塞点，不强行补全。
