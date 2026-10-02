"""provider 目录：各 provider 的默认值与可选模型。

设计意图：**前端不硬编码 provider 与模型名**。`README.md` 第 3.2 节特别提醒
「模型供应商会更新模型名和推荐版本，前端 provider 列表由后端配置返回」，
因此这里集中维护一份目录，由 `GET /api/config/providers` 暴露给前端，
将来新增 provider 或调整推荐模型只改这一个文件。

**本系统只支持远程 Provider**：本地模型方案已于 2026-10-02 整体移除（本地权重加载、
进程级缓存、`local` 取值与环境变量路径一并删除），因此每个 provider 都需要 API Key，
这里也不再需要"该 provider 是否需要 Key"这类判断。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


class LLMProvider(StrEnum):
    """LLM provider。两者都是远程服务，通过官方 SDK 或 OpenAI 兼容接口调用。"""

    DEEPSEEK = "deepseek"
    QWEN = "qwen"


class EmbedProvider(StrEnum):
    """Embedding provider（仅远程）。"""

    QWEN = "qwen"


class RerankProvider(StrEnum):
    """Reranker provider（仅远程）。"""

    QWEN = "qwen"


class ProviderOption(TypedDict):
    """单个 provider 的可选项描述。"""

    value: str
    label: str
    default_base_url: str | None
    default_model: str
    suggested_models: list[str]


# provider 默认值表。
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
            "label": "Qwen",
            "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "qwen-plus",
            "suggested_models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
        },
    ],
    "embed": [
        {
            "value": EmbedProvider.QWEN.value,
            "label": "Qwen",
            "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "text-embedding-v4",
            "suggested_models": ["text-embedding-v4", "text-embedding-v3"],
        },
    ],
    "rerank": [
        {
            "value": RerankProvider.QWEN.value,
            "label": "Qwen",
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
