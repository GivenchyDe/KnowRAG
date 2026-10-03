"""全局模型配置的请求体与响应体。

契约来源：`docs/DESIGN_IMPLEMENTATION.md` 第 6.2 节。
所有响应**只返回脱敏后的 API Key**，明文与密文都不出现在响应里。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # 向量模型的接口地址。只有 provider 为 custom 时才有意义（其余 provider 的
    # 端点由代码固定或目录给出），因此它同时是"界面是否需要用户填地址"的判据。
    embed_base_url: str | None
    embed_model: str
    # 后端按模型**实测**值维护（见 index_service.sync_embedding_dimension），
    # 请求体里不存在该字段；返回它是为了让运维与状态接口能看到当前生效的维度。
    embed_dimension: int

    rerank_provider: str
    rerank_api_key_masked: str | None
    rerank_base_url: str | None
    rerank_model: str

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
    # 只有 provider = custom 时才需要：其余 provider 的向量端点由代码固定
    # （qwen）或由目录给出（zhipu / siliconflow），用户填了也不会被使用，
    # 因此界面上只在 custom 时显示这个输入框。
    embed_base_url: str | None = None
    embed_model: str | None = None
    # 没有 embed_model_path / embed_dimension：本地模型方案已移除，
    # 向量维度则由后端按实测值维护（`index_service.sync_embedding_dimension`），
    # 前端不提交、也不允许提交。

    rerank_provider: str | None = None
    rerank_api_key: str | None = None
    # 同 embed_base_url：只有 custom 需要。
    rerank_base_url: str | None = None
    rerank_model: str | None = None

    # 已从契约中删除的字段。它们过去都可以提交，现在各有归属：
    #   - embed_dimension：改由后端按模型实测值维护；
    #   - embed_model_path / rerank_model_path：随本地模型方案一起移除。
    _REMOVED_FIELDS: ClassVar[dict[str, str]] = {
        "embed_dimension": "向量维度已改由后端按模型实测值维护，不再接受前端提交",
        "embed_model_path": "本地模型方案已移除，不再有本地 Embedding 模型路径",
        "rerank_model_path": "本地模型方案已移除，不再有本地 Reranker 模型路径",
    }

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_fields(cls, data: Any) -> Any:
        """拒绝请求体里已被删除的字段。

        为什么不静默忽略（pydantic 的默认行为）：这些字段以前是可填的，静默忽略会让
        调用方（尤其是没跟着升级的前端）以为"设置生效了"。显式 422 至少能让人立刻发现
        契约变了——"以为改了就生效"正是本次清理要消灭的那类误解。
        """
        if isinstance(data, dict):
            for field, message in cls._REMOVED_FIELDS.items():
                if field in data:
                    raise ValueError(message)
        return data

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

    @field_validator("llm_base_url", "embed_base_url", "rerank_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str | None) -> str | None:
        """base_url 去掉首尾空白；只有空白视同"没填"。

        不能把纯空白原样存进库：它非空、因而会被当成"已填地址"，
        拼出来的请求地址就成了 `" /chat/completions"` 这种形态，
        报错信息只会指向网络问题，排查成本很高。
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


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
    """provider 目录项。

    曾经还有一个 `models` 字段（预设模型列表，供前端 `<datalist>` 做建议下拉）：
    界面改成纯手输之后它没有消费方了，2026-10-04 删除。需要建议列表时应当
    自绘候选面板或改用 Element Plus 的 `el-autocomplete`（原生 `datalist`
    右端的箭头无法用 CSS 隐藏，见 `docs/UI_DESIGN_PROMPT.md` 第 5 节）。
    """

    value: str
    label: str
    # None 表示没有可直接使用的默认地址：或由代码固定（qwen 的向量/重排端点），
    # 或必须由用户填写（custom）。
    default_base_url: str | None
    # custom 为空字符串：没有可推荐的默认模型，必须由用户填写。
    default_model: str
    # 该 provider 的地址是否必须由用户填写（当前只有 custom 为 True）。
    # 前端据此决定是否显示地址输入框——**不要**用 `default_base_url is None` 代替：
    # qwen 的向量/重排也没有可展示的地址，但端点由代码固定，用户不需要填。
    requires_base_url: bool = False


class ProvidersResponse(BaseModel):
    """GET /api/config/providers 的响应。"""

    llm: list[ProviderOptionResponse]
    embed: list[ProviderOptionResponse]
    rerank: list[ProviderOptionResponse]


class ConnectionTestRequest(BaseModel):
    """POST /api/config/model/test 的请求体。

    `api_key` 由前端传入**用户当前输入框里的值**，而不是从库里读：
    这样用户可以在保存前先验证 Key 是否有效，避免存下一把无效的 Key。

    `use_saved_key=True` 时改用**数据库里已保存的 Key**（用户不必重新粘贴一遍）。
    该能力的安全前提是三条约束同时成立（`docs/DESIGN_IMPLEMENTATION.md` 第 6.2 节）：
    1. 必须登录（接口依赖 `get_current_active_user`）；
    2. **目标地址只取服务端已保存的值**——否则请求方可以把 Key 指向自己的地址，
       凭空造出一条密钥外泄通道（详见 `config_service.load_saved_connection_target`）；
    3. 日志只出现脱敏 Key。
    接口**不得**退化成"用服务端密钥发任意请求"的通用代理。
    """

    kind: ConnectionTestKind
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    # 默认 False：老前端不带这个字段时行为完全不变（向后兼容）。
    use_saved_key: bool = False


class ConnectionTestResponse(BaseModel):
    """连接测试结果。

    刻意不包含供应商返回的原始错误信息：那可能带上账号、额度、请求 ID 等
    敏感细节（`docs/CODING_CONVENTIONS.md` 第 9 节要求不得泄露供应商内部细节）。
    `detail` 只放**本项目自己算出**的诊断信息（如实测向量维度、重排分数），
    **不含任何凭据**。
    """

    success: bool
    code: str
    message: str
    detail: dict[str, Any] | None = None
