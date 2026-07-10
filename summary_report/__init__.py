"""
summary_report — 全域经营分析汇总报告服务。

分层结构：
  core/       核心底层能力（配置 / 数据库 / LLM / 日志 / 安全）
  constants/  常量、表结构描述、业务上下文
  utils/      通用工具
  services/   业务逻辑（NL2SQL 编排 + 四个具体报告服务）
  api/        路由层（Pydantic 模型 + 路由注册）
"""

__version__ = "2.0.0"
