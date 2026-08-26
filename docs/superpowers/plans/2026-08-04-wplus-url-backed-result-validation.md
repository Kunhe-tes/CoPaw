# W+ SOP URL 型结果交付兼容计划

## 目标

允许 `sop_result` 携带 `copy_file_to_static` 返回的实际 URL，不再要求产物 URL 符合平台按 ownership 重建的固定格式，也不再要求四个本地文件内容与事件顶层字段逐字一致。工作台预览以 `artifacts[].static_url` 为唯一文件地址来源。

## 保留的交付校验

- 四个声明的静态文件必须存在于当前 Workspace 的 `static` 目录内。
- 文件解析后的路径不得逃逸 `static` 目录。
- 文件实际 SHA256 必须与事件声明一致。
- `FinalSopResult` / `FinalArtifact` 的结构、四类产物完整性和基础字段约束保持不变。

## 实施步骤

1. 在 `tests/unit/app/wplus_sop/test_service.py` 添加 URL 型顶层结果与非 ownership URL 可被接收的回归测试，并确认修改前失败。
2. 精简 `src/swe/app/wplus_sop/service.py::_validate_delivered_artifacts`，删除 URL 重建比较、UTF-8/JSON 解码和事件内容一致性比较，只保留文件边界、存在性和 SHA256 校验。
3. 扩展后端会话投影，从 `artifact_id=sop_render_md`、`artifact_id=sop_render_html` 的 `static_url` 生成预览地址，不使用顶层 `readable_sop/html` 作为地址来源。
4. 在 `console/src/pages/WPlusSopWorkspace/index.test.tsx` 添加 static URL 型 Markdown/HTML 预览测试，并确认修改前失败。
5. 在 `console/src/pages/WPlusSopWorkspace/index.tsx` 增加 static URL 结果预览：Markdown 地址拉取后按文本显示，HTML 地址使用沙箱 iframe 的 `src`；内联内容继续沿用现有 `pre`/`srcDoc`。
6. 更新 `docs/adr/0013-wplus-sop-uses-persisted-session-and-structured-envelope.md` 的最终交付约束，明确事件引用与本地文件不做内容相等校验。
7. 运行后端定向测试、前端定向测试、静态检查、独立审查循环和 GitNexus 变更检测。

## 验收标准

- 用户提供的最新 payload 形态不再触发 `invalid static URL for artifact`。
- 顶层 `sop_spec.file_url`、`readable_sop`、`html`、`example_result_html` 与 artifacts 指向不同版本名时，不因内容一致性检查失败。
- 缺失文件、目录逃逸或 SHA256 不匹配仍被拒绝。
- `sop_render_md` 的 artifact static URL 显示实际文本；`sop_render_html` 的 artifact static URL 在沙箱 iframe 中加载；原有内联预览保持兼容。
