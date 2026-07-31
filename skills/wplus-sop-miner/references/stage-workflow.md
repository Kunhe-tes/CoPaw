# 逐环节澄清与预跑

## 状态转换

每个环节必须按以下顺序推进：

| 当前状态 | 必须完成的动作 | 下一状态 |
| --- | --- | --- |
| `pending` | 前一环节确认后激活本环节 | `clarifying` |
| `clarifying` | 解决当前问题清单 | `ready_for_trial` |
| `ready_for_trial` | 提交冻结的 `trial_plan`，由 CoPaw 后端启动预跑 | `trial_running` |
| `trial_running` | 后端受控运行能力并提交步骤进度与脱敏结果 | `feedback_review` |
| `feedback_review` | 用户在工作台反馈；有修改则由系统复跑，无修改则请求环节确认 | `ready_for_trial` 或 `awaiting_stage_confirmation` |
| `awaiting_stage_confirmation` | 用户确认当前环节无误 | `confirmed` |
| `confirmed` | 原子切换到下一环节或最终输出 | 下一环节 `clarifying` 或 `finalizing` |

预跑不可跳过。用户可以用“已按步骤验证，无反馈”一次完成反馈和确认，但必须留下该确认记录。

## 进入预跑的条件

当前环节适用的入口、输入、范围、口径、规则、输出和下一动作都已确认、明确未知或不适用后：

1. 把 `question_resolved` 更新为 `question_total`；
2. 把环节设为 `ready_for_trial`；
3. 提交 `trial_plan`，冻结能力版本、输入快照、步骤、授权要求和脱敏输出
   契约；
4. 由 CoPaw 后端运行时启动当前环节预跑，不得开始下一环节。

## 结构化预跑计划

```json
{
  "kind": "trial_plan",
  "payload": {
    "stage_id": "stage_...",
    "input_snapshot_id": "snapshot_...",
    "steps": [
      {
        "step_id": "step_...",
        "capability_name": "能力名称",
        "adapter": "适配器",
        "command": "命令",
        "verification_status": "verified",
        "input_sources": ["已确认输入"],
        "requires_approval": false
      }
    ],
    "redaction_contract": {
      "allow": ["counts", "schema_validation", "warnings", "failure_location"],
      "deny": ["raw_customer_response", "account_values", "free_text_notes"]
    }
  }
}
```

当执行分类为 `opencli` 时，平台按计划在有权限的后端环境执行对应能力。
当分类为 `analysis` 时，使用已确认输入或前序脱敏输出；`human_action` 只生成
明确人工交接；`unsupported` 必须停在阻塞状态。任何分类都不得伪造 OpenCLI
或声称未执行的步骤成功。

## 反馈闭环

- 把反馈归入当前环节的入口、范围、口径、规则、输出或下一动作。
- 只在 `trial_notes` 中保留脱敏的流程反馈，不保存真实客户值或原始响应。
- 若反馈改变流程，提交 `trial_feedback_accepted`，把环节设回
  `ready_for_trial`，由平台创建带 `rerun_of_run_id` 的新运行并重新执行当前
  环节；重复提交同一 command 不得创建多个新 run。
- 若反馈没有改变流程，把环节设为 `awaiting_stage_confirmation`。
- 用户在工作台接受预跑结果后进入 `awaiting_stage_confirmation`；只有随后
  的明确环节确认命令可把它设为 `confirmed`。

## 不得遗忘的环节切换

确认当前环节时执行一个不可拆分的切换动作：

1. 当前环节设为 `confirmed`，`verification_mode` 设为 `user_confirmed`；
2. 若存在下一环节：把下一环节设为 `clarifying`，更新
   `current_stage_id` 和 `next_required_transition=ask_stage_questions`；
3. 提交 `stage_confirmed`。平台在同一原子转换中激活下一环节，并启动新的
   Miner 回合生成下一环节首轮 `question_batch`；本事件不得夹带未校验题组。

只有最后一个环节确认后，才把 `next_required_transition` 设为
`finalize_outputs`。最终输出校验完成前不得进入记忆授权。
