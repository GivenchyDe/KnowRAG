"""provider 目录：各 provider 的默认值与可选模型。

设计意图：**前端不硬编码 provider 与模型名**。`README.md` 第 3.2 节特别提醒
「模型供应商会更新模型名和推荐版本，前端 provider 列表由后端配置返回」，
因此这里集中维护一份目录，由 `GET /api/config/providers` 暴露给前端，
将来新增 provider 或调整推荐模型只改这一个文件。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


class LLMProvider(StrEnum):
    """LLM provider。"""

    DEEPSEEK = "deepseek"
    QWEN = "qwen"


class EmbedProvider(StrEnum):
    """Embedding provider。`local` 表示加载本地模型，`qwen` 表示调用远程接口。"""

    LOCAL = "local"
    QWEN = "qwen"


class RerankProvider(StrEnum):
    """Reranker provider，取值含义同 EmbedProvider。"""

    LOCAL = "local"
    QWEN = "qwen"


class ProviderOption(TypedDict):
    """单个 provider 的可选项描述。"""

    value: str
    label: str
    default_base_url: str | None
    default_model: str
    suggested_models: list[str]


# provider 默认值表。base_url 为 None 表示该 provider 不使用网络地址（本地模型）。
_PROVIDER_CATALOG: dict[str, list[ProviderOption]] = {
    "llm": [
        {
            "value": LLMProvider.DEEPSEEK.value,
            "label": "DeepSeek",
            "default_base_url": "https://api.deepseek.com",
            "default_model": "deepseek-chat",
            # 只列稳定可用的模型名，不追「最新版本」——供应商改名时由这里统一调整。
            "suggested_models": ["deepseek-chat", "deepseek-reasoner"],
        },
        {
            "value": LLMProvider.QWEN.value,
            "label": "通义千问（Qwen）",
            "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "qwen-plus",
            "suggested_models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
        },
    ],
    "embed": [
        {
            "value": EmbedProvider.LOCAL.value,
            "label": "本地模型",
            "default_base_url": None,
            "default_model": "BAAI/bge-m3",
            "suggested_models": ["BAAI/bge-m3", "BAAI/bge-large-zh-v1.5"],
        },
        {
            "value": EmbedProvider.QWEN.value,
            "label": "通义千问（远程）",
            "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "text-embedding-v4",
            "suggested_models": ["text-embedding-v4", "text-embedding-v3"],
        },
    ],
    "rerank": [
        {
            "value": RerankProvider.LOCAL.value,
            "label": "本地模型",
            "default_base_url": None,
            "default_model": "bge-reranker-large",
            "suggested_models": ["bge-reranker-large", "bge-reranker-v2-m3"],
        },
        {
            "value": RerankProvider.QWEN.value,
            "label": "通义千问（远程）",
            "default_base_url": "https://dashscope.aliyuncs.com/api/v1",
            "default_model": "gte-rerank-v2",
            "suggested_models": ["gte-rerank-v2"],
        },
    ],
}


def get_catalog() -> dict[str, list[ProviderOption]]:
    """返回完整 provider 目录，供接口层直接序列化。

    返回副本而不是内部对象：调用方拿到后可能按前端需要裁剪字段，
    不能让它们改到全局目录。
    """
    return {kind: [dict(option) for option in options] for kind, options in _PROVIDER_CATALOG.items()}


def default_for(kind: str, provider: str) -> ProviderOption | None:
    """按类别与 provider 取值查出目录项。找不到返回 None。"""
    for option in _PROVIDER_CATALOG.get(kind, []):
        if option["value"] == provider:
            return dict(option)
    return None


def supported_values(kind: str) -> set[str]:
    """返回某类别下所有合法 provider 取值，用于请求校验。"""
    return {option["value"] for option in _PROVIDER_CATALOG.get(kind, [])}
