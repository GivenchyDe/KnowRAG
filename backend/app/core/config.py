"""应用配置。

所有运行期配置统一从环境变量 / `.env` 读取，代码中不硬编码密钥。
`Settings` 实例通过 `get_settings()` 以 lru_cache 缓存，保证进程内只解析一次配置。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """KnowRAG 后端配置项。

    字段名与 `.env` 中的大写变量名大小写不敏感地一一对应（例如 `app_env` ↔ `APP_ENV`）。
    """

    model_config = SettingsConfigDict(
        # 环境变量优先于 .env 文件，便于容器环境覆盖镜像内默认值。
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- 运行环境 ---
    app_env: str = Field(default="development", description="development / production")
    app_name: str = Field(default="KnowRAG", description="应用名，用于文档标题与日志")
    app_version: str = Field(default="0.1.0", description="应用版本")
    log_level: str = Field(default="INFO", description="日志级别")
    debug: bool = Field(default=False, description="调试模式，生产环境必须为 false")

    # --- 安全（Phase 1 / Phase 2 使用，Phase 0 仅做配置占位与校验）---
    jwt_secret: str = Field(default="change-me", description="JWT 签名密钥")
    jwt_expire_minutes: int = Field(default=30, description="access token 有效期（分钟）")
    fernet_key: str = Field(default="", description="API Key 对称加密密钥，需为合法 Fernet key")

    # --- 数据库与向量库（Phase 1 / Phase 3 使用）---
    # 数据库选型偏离说明：docs/DESIGN_IMPLEMENTATION.md 原定 PostgreSQL，
    # 但本机只提供 MySQL 8.0（数据目录通过 DataGrip 管理），且 7 张业务表均为
    # 「主键 + 外键 + 时间戳 + 少量 JSON」的常规结构，未使用任何 PostgreSQL 专有能力
    # （数组类型、jsonb 的 GIN 索引、全文检索、PostGIS），因此切换为 MySQL 无架构损失。
    # 对应调整：jsonb -> JSON、timestamptz -> DATETIME，且全库使用 utf8mb4_0900_ai_ci
    # 排序规则（大小写不敏感），避免 username / email 唯一约束被大小写变体绕过。
    database_url: str = Field(
        default="mysql+pymysql://root:123456@127.0.0.1:3306/knowrag?charset=utf8mb4",
        description="关系数据库连接串",
    )
    chroma_host: str = Field(default="localhost", description="Chroma 服务地址")
    chroma_port: int = Field(default=8000, description="Chroma 服务端口")

    # --- 本地模型路径（Phase 2 / Phase 4 使用）---
    local_bge_m3_path: str = Field(default="", description="本地 bge-m3 模型目录")
    local_bge_reranker_path: str = Field(default="", description="本地 bge-reranker-large 模型目录")

    # --- CORS ---
    # 用字符串而非 list 接收：环境变量天然是字符串，pydantic-settings 对 list 字段会先尝试
    # JSON 解析，要求使用者写 `["a","b"]` 这种反直觉的格式。这里改用逗号分隔，
    # 再通过 cors_origin_list 属性切分。
    cors_origins: str = Field(
        default="http://localhost:5173",
        description="允许跨域的前端来源白名单，多个用英文逗号分隔；生产环境必须收紧为真实域名",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的 CORS 白名单切分为列表。"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """是否为生产环境。生产环境需要更严格的默认行为（如关闭 /docs）。"""
        return self.app_env.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程级单例配置。"""
    return Settings()
