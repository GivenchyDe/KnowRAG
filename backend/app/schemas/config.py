"""全局模型配置的请求体与响应体。

契约来源：`docs/DESIGN_IMPLEMENTATION.md` 第 6.2 节。
所有响应**只返回脱敏后的 API Key**，明文与密文都不出现在响应里。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 允许的连接测试目标。用 Literal 而不是自由字符串，避免接口被当成
# 「任意地址探测工具」使用。
ConnectionTestKind = Literal["llm", "embed", "rerank"]


class ModelConfigResponse(BaseModel):
    """GET /api/config/model 的响应。"""

    model_config = ConfigDict(from_attributes=True)

    llm_provider: str
    # 脱敏后的 Key，形如 `sk-****abcd`；从未填写时为 null
    llm_api_key_masked: str | None
    llm_base_url: str | None
    llm_model: str
    llm_temperature: float
    llm_max_tokens: int

    embed_provider: str
    embed_api_key_masked: str | None
    embed_model: str
    # 本地模型目录属于部署信息，不是密钥，可以返回；未配置时由后端用环境变量兜底
    embed_model_path: str | None
    embed_dimension: int

    rerank_provider: str
    rerank_api_key_masked: str | None
    rerank_model: str
    rerank_model_path: str | None

    updated_at: datetime | None


class ModelConfigUpdate(BaseModel):
    """PUT /api/config/model 的请求体。

    行为约定：
    - 未提供的字段（`None`）表示**保持原值不变**；这是为了让前端可以只提交
      用户实际改动的部分，避免读取-修改-写回过程中覆盖掉并发修改；
    - API Key 字段额外支持显式清空：空字符串 `""` 表示**删除已保存的 Key**，
      未提供或提供 `None` 表示保持原 Key（对应设计文档第 4.2 节的「空 Key 保持原 Key」）；
    - 因此前端要清空 Key 时必须显式传 `""`，不能传 `null`。
    """

    llm_provider: str | None = None
    llm_api_key: str | None = Field(
        default=None,
        description="新的 API Key；传空字符串表示清除已保存的 Key",
    )
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    llm_max_tokens: int | None = Field(default=None, ge=1, le=131072)

    embed_provider: str | None = None
    embed_api_key: str | None = None
    embed_model: str | None = None
    embed_model_path: str | None = None
    embed_dimension: int | None = Field(default=None, ge=1, le=8192)

    rerank_provider: str | None = None
    rerank_api_key: str | None = None
    rerank_model: str | None = None
    rerank_model_path: str | None = None

    @field_validator("llm_model", "embed_model", "rerank_model")
    @classmethod
    def _reject_blank_model(cls, value: str | None) -> str | None:
        """模型名不允许为空白字符串。

        模型名是必填项，传空会导致后续创建实例时拿到无意义的取值，
        这类错误放在请求校验阶段拦截比在 Phase 4 调用模型时报错更早、更容易定位。
        """
        if value is not None and not value.strip():
            raise ValueError("模型名不能为空")
        return value


class ModelConfigUpdateResponse(BaseModel):
    """PUT /api/config/model 的响应。

    契约来自设计文档第 6.2 节，其中 `index_stale` 用于提示前端
    「Embedding 配置变了，需要重建知识库索引」。
    """

    status: str = "success"
    # Embedding 相关配置变化时为 true；无需重建索引的变更（仅 LLM / Reranker）为 false
    index_stale: bool = False
    message: str


class ProviderOptionResponse(BaseModel):
    """provider 目录项。"""

    value: str
    label: str
    default_base_url: str | None
    default_model: str
    suggested_models: list[str]


class ProvidersResponse(BaseModel):
    """GET /api/config/providers 的响应。"""

    llm: list[ProviderOptionResponse]
    embed: list[ProviderOptionResponse]
    rerank: list[ProviderOptionResponse]


class ConnectionTestRequest(BaseModel):
    """POST /api/config/model/test 的请求体。

    `api_key` 由前端传入**用户当前输入框里的值**，而不是从库里读：
    这样用户可以在保存前先验证 Key 是否有效，避免存下一把无效的 Key。
    """

    kind: ConnectionTestKind
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ConnectionTestResponse(BaseModel):
    """连接测试结果。

    刻意不包含供应商返回的原始错误信息：那可能带上账号、额度、请求 ID 等
    敏感细节（`docs/CODING_CONVENTIONS.md` 第 9 节要求不得泄露供应商内部细节）。
    """

    success: bool
    code: str
    message: str
