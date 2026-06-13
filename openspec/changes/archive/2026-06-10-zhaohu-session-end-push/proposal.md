## Why

招乎渠道用户需要在会话结束后自动收到结果推送通知，以便及时了解会话执行情况。目前招乎渠道缺少此功能，用户无法在会话结束时获得主动通知。

## What Changes

- 在招乎渠道配置中新增 `session_end_push_enabled` 开关字段，默认关闭
- 前端招乎渠道配置页新增"会话结束推送"开关组件
- 开关字段加入现有的分发逻辑，支持将配置分发到其他租户
- 后端 `ZhaohuChannel` 在会话完成时检查开关状态，若开启则调用招乎 API 推送结果

## Capabilities

### New Capabilities

- `zhaohu-session-end-push`: 招乎渠道会话结束推送功能，包含配置开关、分发支持、推送触发逻辑

### Modified Capabilities

无

## Impact

- **后端**:
  - `src/swe/config/config.py`: `ZhaohuConfig` 新增 `session_end_push_enabled` 字段
  - `src/swe/app/channels/zhaohu/channel.py`: 重写 `_on_process_completed` 方法实现推送

- **前端**:
  - `console/src/api/types/channel.ts`: `ZhaohuConfig` interface 新增字段
  - `console/src/pages/Control/Channels/components/ChannelDrawer.tsx`: 新增开关组件、更新分发字段列表
  - `console/src/locales/`: 新增 i18n 翻译
