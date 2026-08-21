# W+ SOP 最终产出阶段协议修复计划

## 问题

最终环节确认后进入 `FinalizingOutputs`，但运行命令没有声明允许事件和完成顺序。Agent 在 `retry_current_turn` 中据命令名称自行推断出不存在的 `retry_started`，服务端拒绝后未能完成 `sop_result`，回合最终进入可恢复失败。

## 决策

- 首次进入最终阶段必须在同一后台回合依次持久化 `sop_result`、`memory_candidates`。
- 若前一回合已经成功持久化 `sop_result`，重试仅补 `memory_candidates`，不得重复覆盖最终结果。
- 服务端在重试载荷中提供 `final_result_persisted`，Agent 不从文本或历史消息猜测。
- 明确禁止不存在的 `retry_started`；失败工具调用可按服务端返回的 allowed events 修正后重试。

## 测试

- `tests/unit/app/wplus_sop/test_runtime.py`：首次最终化的事件序列；已保存结果后的重试序列；禁止 `retry_started`。
- `tests/unit/app/wplus_sop/test_service.py`：重试载荷的 `final_result_persisted` 由服务端状态决定，忽略客户端伪造值。
- 运行 W+ model/service/runtime/router 全量测试、前端工作台测试和构建。
