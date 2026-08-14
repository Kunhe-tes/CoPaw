# HTML 预览事件维度设计

## 目标

在保留原 HTML 按钮点击统计的基础上，让同一张事件明细表能够记录：

- 主方案弹窗查看；
- 二次弹窗中的子方案查看；
- 原有按钮点击；
- 二次弹窗内具体模块曝光。

每次行为仍新增一条 `swe_html_preview_click_events` 记录，不更新模板、
名单快照或之前的事件。

## 字段约定

| 字段 | 说明 |
|------|------|
| `event_type` | `button_click`、`main_preview_view`、`sub_preview_view`、`module_exposure` |
| `template_id/result_id` | 当前事件所在模板及其生成结果；模块事件指向当前子模板 |
| `root_template_id/root_result_id` | 本次预览入口的主模板及其生成结果；主模板事件与当前模板相同 |
| `event_target_id/name` | 模块等模板内具体曝光对象的稳定标识与展示名称 |
| `trace_id` | 方案生成与浏览链路标识；同一链路的事件应传相同值 |

原有 `button_id/name/text/type` 只描述按钮，不复用为模板或模块标识。
原有 `file_url/name`、`list_key/name`、客户、任务、用户及机构字段继续承担
HTML 和业务上下文关联，但可视化查询不依赖解析 URL 获得模板 ID。

`template_id` 是对模板记录的逻辑引用，不建立数据库外键。即使模板记录
被删除，历史事件仍应保留；`file_name` 等字段同时作为事件发生时的名称快照。

为兼容现有表结构和查询，`clicked_at` 继续作为所有类型事件的发生时间；
上报方可显式传入，未传时由后端使用当前时间。非 `button_click` 事件不做
按钮分类，`button_type` 保持为空。

## 兼容策略

- `event_type` 为 `NOT NULL DEFAULT 'button_click'`，旧记录和旧客户端无需回填。
- 四个模板关联字段允许为空，旧按钮点击继续兼容；新的主方案、子方案和模块
  事件必须传当前模板与结果。主方案事件未传 `root_*` 时由后端补成当前模板，
  子方案和模块事件必须显式传主模板与主结果。
- 写接口只接受四个受控事件类型，避免看板出现拼写不同的同义事件。
- 原按钮汇总、名单汇总和客户汇总显式过滤 `event_type='button_click'`。
- `GET /api/html-preview/events` 支持 `event_type` 查询参数并返回新增字段；
  未传参数时默认查询 `button_click`，保持旧点击明细接口语义。
- 明细接口传 `event_type=all` 时查询全部事件类型；可按当前模板、主模板、
  结果、模块和链路字段筛选，并通过 `limit/offset` 分批读取。

## 上报示例

模块曝光：

```json
{
  "file_url": "https://example.com/plan.html",
  "event_type": "module_exposure",
  "template_id": 12,
  "result_id": "result-sub",
  "root_template_id": 11,
  "root_result_id": "result-main",
  "event_target_id": "module-customer-profile",
  "event_target_name": "客户核心信息",
  "trace_id": "trace-001"
}
```

子方案查看把 `event_type` 改为 `sub_preview_view`，当前模板字段写子模板，
`root_*` 写入口主模板。主方案查看使用 `main_preview_view`，当前模板字段写
主模板，`root_*` 可省略并由后端自动补齐。按钮点击继续兼容不传模板字段。

## 迁移与发布顺序

1. 先且仅执行一次 `scripts/sql/html_preview_event_dimensions_migration.sql`
   扩展表结构。
2. 再部署包含新字段写入逻辑的后端。
3. 最后逐步接入主方案、子方案和模块曝光上报方。

新增字段均有默认值或允许为空，旧版本前端与新版本后端可以并行运行。
现有表数据量较大时，应先在对应 MySQL 版本验证在线建索引能力，并选择低峰期
执行迁移。
