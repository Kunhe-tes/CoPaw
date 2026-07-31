# SOP 输出约定

只有所有环节都完成各自的澄清、预跑、反馈和确认后，才生成最终文件。

## 1. 机器可读规格

创建符合 `sop-schema.json` 的 `sop_spec.json`：

- 保留用户确认的环节顺序；
- 每个完成环节的 `verification_mode` 必须为 `user_confirmed`；
- `trial_notes` 只保留脱敏的流程反馈；
- 每个环节只分类为 `opencli`、`analysis`、`human_action` 或 `unsupported`；
- `capability_snapshot` 只包含环节实际引用的能力；
- 参数来源只记录为 `constant`、`user_input` 或 `stage_output`；
- 不得包含对话全文、客户级数据或原始响应。

先运行 `scripts/validate_sop.py sop_spec.json`；验证失败时修复后重跑。

## 2. 可读版 SOP

使用：

- `scripts/render_md.py` 生成 `sop_render.md`；
- `scripts/render_sop.py` 生成 `sop_render.html`。

内容至少包括触发条件、角色、适用范围（由请求摘要与各环节数据范围表达）、有序环节、页面或人工入口、判断规则、输出、下一动作、执行分类、预跑确认状态和脱敏反馈。

## 3. 示例结果 HTML

模板目录约定为 `assets/example-result-templates/`。用户后续添加模板后：

1. 读取与当前 SOP 输出类型最匹配的 HTML 模板；
2. 从各环节预跑中提取用户允许使用的脱敏字段、汇总指标和示例结构；
3. 按模板生成 `example_result.html`，展示这套 SOP 的示例结果；
4. 保留模板布局和样式，不添加远程资源，不嵌入原始响应，不写入真实客户标识或交易明细；
5. 检查 HTML 可独立打开、文本已转义、空数据和缺失字段有明确状态。

模板目录不存在、为空或没有匹配模板时，不得凭空创造模板或静默跳过；明确提示模板阻塞，等待模板补充后再生成示例结果。

## 4. 复制到 static

最终必须交付四个文件：

| 文件 | 用途 |
| --- | --- |
| `sop_spec.json` | 机器可读 SOP |
| `sop_render.md` | Markdown SOP |
| `sop_render.html` | SOP 静态视图 |
| `example_result.html` | 基于模板和脱敏预跑数据的示例结果 |

对每个文件逐一调用 `copy_file_to_static`：

1. 传入生成文件的实际路径；
2. 确认工具成功并返回 `static` 中的目标路径；
3. 只把工具返回的静态路径作为最终交付地址；
4. 不得用 shell、普通复制工具或手写路径代替；
5. 任一文件复制失败时重试或明确报告失败，不得声称全部文件已进入 `static`。

## 5. 记忆候选

四个文件生成并复制完成后，才列出记忆候选。候选只是写入提议；逐项附用户证据并请求批准，再按 `memory-policy.md` 处理。
