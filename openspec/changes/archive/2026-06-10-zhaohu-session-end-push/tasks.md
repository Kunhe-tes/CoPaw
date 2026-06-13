## 1. 后端配置层

- [x] 1.1 在 `src/swe/config/config.py` 的 `ZhaohuConfig` 类中新增 `session_end_push_enabled: bool = False` 字段

## 2. 前端类型与表单

- [x] 2.1 在 `console/src/api/types/channel.ts` 的 `ZhaohuConfig` interface 中新增 `session_end_push_enabled?: boolean`
- [x] 2.2 在 `console/src/pages/Control/Channels/components/ChannelDrawer.tsx` 招乎表单区域新增"会话结束推送"Switch 组件
- [x] 2.3 在 `ChannelDrawer.tsx` 招乎分发配置的 `fields` 数组中新增 `"session_end_push_enabled"`

## 3. 后端推送逻辑

- [x] 3.1 在 `src/swe/app/channels/zhaohu/channel.py` 的 `ZhaohuChannel` 中重写 `_on_process_completed` 方法，检查 `session_end_push_enabled` 开关，开启时调用 `self.send()` 推送结果，异常捕获并记录日志

## 4. 国际化

- [x] 4.1 在 `console/src/locales/` 下相关语言文件中新增 `session_end_push_enabled` 的翻译 key
