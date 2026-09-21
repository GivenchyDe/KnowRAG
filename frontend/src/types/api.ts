/**
 * 前端统一类型定义。
 *
 * Phase 0 只定义与健康检查相关的类型；用户、配置、文档、索引、聊天等类型
 * 在对应 Phase 实现接口时按 docs/DESIGN_IMPLEMENTATION.md 第 6 节的契约补充。
 */

/** 后端健康检查响应，对应 GET /health */
export interface HealthResponse {
  status: string;
}
