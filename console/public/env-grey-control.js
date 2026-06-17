/*
 * ============================================================
 * Author: Kun He
 * Description: 运行时配置
 * Date: 2026-04-07
 * ============================================================
 */
window.__env__ = {
  baseUrl: "", // nginx将动态替换这里的内容
  serviceUnitId: '',
  env: '',
  systemCode: '',
  systemSect: '',
  responseFeedbackUserWhitelist: ["*"], // 回答反馈卡片白名单，"*"表示全员开放
  chatSessionPageSize: 100, // 聊天历史分页大小，未配置或非法时默认100
};
