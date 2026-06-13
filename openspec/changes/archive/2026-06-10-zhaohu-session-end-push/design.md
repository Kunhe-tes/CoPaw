## Context

招乎(Zhaohu)是项目支持的即时通讯渠道之一，已有完整的消息推送能力（`ZhaohuChannel.send()` 方法）。当前招乎渠道配置包含 `robot_open_id`、`client_id`、`client_secret` 等字段，前端支持将这些字段分发到其他租户。

会话完成后，`BaseChannel` 基类会调用 `_on_process_completed` 钩子方法，子类可重写该方法实现自定义逻辑。`ZhaohuChannel` 目前未重写此方法。

## Goals / Non-Goals

**Goals:**
- 在招乎渠道配置中新增 `session_end_push_enabled` 开关，默认关闭
- 开关支持通过现有分发逻辑分发到其他租户
- 会话结束时若开关开启，自动通过招乎 API 推送结果通知

**Non-Goals:**
- 不修改其他渠道的推送逻辑
- 不新增独立的推送 API 端点
- 不改变现有招乎消息推送的 payload 格式

## Decisions

### 1. 使用 `_on_process_completed` 钩子触发推送

**选择**: 重写 `ZhaohuChannel._on_process_completed` 方法

**替代方案**: 使用 `HookEventName.STOP` hook — 但 hook 机制是全局的，不适合渠道级别的开关控制

**理由**: `_on_process_completed` 是 `BaseChannel` 提供的渠道级钩子，天然与渠道绑定，且已有 `send()` 方法可直接复用

### 2. 复用现有 `send()` 方法推送

**选择**: 直接调用 `self.send()` 推送会话结果

**理由**: `ZhaohuChannel.send()` 已封装了招乎 API 的推送逻辑（构造 payload、POST 到 push_url），无需重复实现

### 3. 开关字段加入分发列表

**选择**: 将 `session_end_push_enabled` 加入招乎渠道的 `fields` 分发列表

**理由**: 与现有分发逻辑一致，租户管理员可一键将开关配置同步到所有目标租户

## Risks / Trade-offs

- [推送失败不影响会话结果] → `_on_process_completed` 中推送异常应捕获并记录日志，不抛出异常
- [开关默认关闭] → 现有租户不受影响，需手动开启
