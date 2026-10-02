"""provider 目录：各 provider 的默认值与预设模型列表。

设计意图：**前端不硬编码 provider 与模型名**。`README.md` 第 3.2 节特别提醒
「模型供应商会更新模型名和推荐版本，前端 provider 列表由后端配置返回」，
因此这里集中维护一份目录，由 `GET /api/config/providers` 暴露给前端，
将来新增 provider 或调整推荐模型只改这一个文件。

**本系统只支持远程 Provider**：本地模型方案已于 2026-10-02 整体移除（本地权重加载、
进程级缓存、`local` 取值与环境变量路径一并删除），因此每个 provider 都需要 API Key，
这里也不再需要"该 provider 是否需要 Key"这类判断。

## 预设模型是「预设 + 手动输入」的混合方案

`models` 只是**下拉建议**，不是白名单：前端用 `<datalist>` 呈现它，用户可以直接
输入列表里没有的模型 ID，后端也不做校验（供应商上新的速度远快于本项目发版）。
因此新增/淘汰模型只需要改本文件，不需要动前端，也不会拦住想用新模型的用户。

`recommended` 标记该 provider 的推荐型号：前端把它排在列表最前并加标记，
`default_model` 也应当与它一致——否则"切换到该 provider 时自动填的模型"
与"列表里标着推荐的模型"会不是同一个，用户会以为是 bug。

## base_url 的三种情况

1. **有默认地址**（deepseek / qwen / zhipu / mimo / siliconflow）：填在
   `default_base_url`，前端在未显式填写时代入；
2. **地址由代码固定、不暴露给用户**（Embedding / Reranker 的 qwen）：
   DashScope 的向量与重排走的是专属端点（`/compatible-mode/v1` 与
   `/api/v1/services/rerank/...`），形状与 OpenAI 兼容接口不同，
   因此 `default_base_url` 为 `None`——**不编一个"看起来能用"的地址出来**
   （那种值会被写进配置、被前端回显，却与实际调用地址无关）；
3. **必须由用户提供**（`custom`）：`default_base_url` 为 `None`，
   由 `requires_explicit_base_url()` 标出，配置层会要求用户填写。

## 地址与模型名的来源（2026-10-02 核对）

`deepseek-v4-pro` / `deepseek-v4-flash`、智谱 `https://open.bigmodel.cn/api/paas/v4`、
硅基流动 `https://api.siliconflow.cn/v1` 均按各家官方文档核对后写入；
MiMo 的 `https://api.xiaomimimo.com/v1` 来自其官方开放平台说明。
**注意**：`deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 下线，
迁移脚本会把库里残留的这两个旧名改写为 `deepseek-v4-pro`（见
`alembic/versions/*_add_embed_rerank_base_url*.py`）。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

# 三类 provider 里都存在的"自定义端点"取值：目录里没有默认地址与预设模型，
# 全部由用户填写。用常量而不是散落的字面量，避免各处拼错后静默走错分支。
CUSTOM_PROVIDER = "custom"


class LLMProvider(StrEnum):
    """LLM provider。全部走 OpenAI 兼容的 `/chat/completions`（qwen 走官方 SDK）。"""

    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    ZHIPU = "zhipu"
    MIMO = "mimo"
    SILICONFLOW = "siliconflow"
    CUSTOM = CUSTOM_PROVIDER


class EmbedProvider(StrEnum):
    """Embedding provider（仅远程）。"""

    QWEN = "qwen"
    ZHIPU = "zhipu"
    SILICONFLOW = "siliconflow"
    CUSTOM = CUSTOM_PROVIDER


class RerankProvider(StrEnum):
    """Reranker provider（仅远程）。"""

    QWEN = "qwen"
    ZHIPU = "zhipu"
    SILICONFLOW = "siliconflow"
    CUSTOM = CUSTOM_PROVIDER


class ModelOption(TypedDict):
    """一个预设模型。

    `value` 是提交给供应商的模型 ID（原样透传，大小写敏感——硅基流动的
    `Qwen/Qwen3-32B` 这类 ID 带组织前缀且区分大小写）；
    `label` 是下拉里给人看的名字。
    """

    value: str
    label: str
    recommended: bool


class ProviderOption(TypedDict):
    """单个 provider 的可选项描述。"""

    value: str
    label: str
    # None 表示"没有可直接使用的默认地址"：或由代码固定（qwen 的向量/重排），
    # 或必须由用户填写（custom）。见模块文档的三种情况。
    default_base_url: str | None
    # custom 为空字符串：没有可推荐的默认值，必须由用户填写。
    default_model: str
    models: list[ModelOption]
    # 该 provider 的地址是否**必须由用户填写**（当前只有 custom 为 True）。
    # 放进目录而不是让前端判断 provider 名：前端不硬编码 provider 与模型名
    # （README 3.2），由后端把"要不要显示地址输入框"这件事作为数据告诉它。
    # 注意它和 `default_base_url is None` 不是一回事：qwen 的向量/重排也没有
    # 可展示的地址，但端点由代码固定，用户既不需要也不能填。
    requires_base_url: bool


# --- 各家默认地址（避免同一个地址在多处重复书写）------------------------------- #
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_QWEN_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
_MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
# 硅基流动有两个平台，**地址必须与 Key 的签发平台一致**：
#   siliconflow.cn 签发的 Key → https://api.siliconflow.cn/v1
#   siliconflow.com 签发的 Key → https://api.siliconflow.com/v1
# 这里取国内平台（本项目其余默认端点也都是国内节点）。持有 .com Key 的用户
# 用 `custom` + `https://api.siliconflow.com/v1` 即可，重排与向量的请求形状相同。
_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"


# provider 默认值表。
_PROVIDER_CATALOG: dict[str, list[ProviderOption]] = {
    "llm": [
        {
            "value": LLMProvider.DEEPSEEK.value,
            "label": "DeepSeek",
            "default_base_url": _DEEPSEEK_BASE_URL,
            "default_model": "deepseek-v4-pro",
            "requires_base_url": False,
            "models": [
                {"value": "deepseek-v4-pro", "label": "DeepSeek V4 Pro", "recommended": True},
                {"value": "deepseek-v4-flash", "label": "DeepSeek V4 Flash", "recommended": False},
            ],
        },
        {
            "value": LLMProvider.QWEN.value,
            "label": "Qwen",
            "default_base_url": _QWEN_COMPATIBLE_BASE_URL,
            "default_model": "qwen3.7-plus",
            "requires_base_url": False,
            "models": [
                {"value": "qwen3.7-max", "label": "Qwen3.7 Max", "recommended": False},
                {"value": "qwen3.7-plus", "label": "Qwen3.7 Plus", "recommended": True},
                {"value": "qwen3.7-flash", "label": "Qwen3.7 Flash", "recommended": False},
            ],
        },
        {
            "value": LLMProvider.ZHIPU.value,
            "label": "智谱 GLM",
            "default_base_url": _ZHIPU_BASE_URL,
            "default_model": "glm-4-plus",
            "requires_base_url": False,
            "models": [
                {"value": "glm-4-plus", "label": "GLM-4 Plus", "recommended": True},
                {"value": "glm-4-air", "label": "GLM-4 Air", "recommended": False},
                {"value": "glm-4-flash", "label": "GLM-4 Flash", "recommended": False},
            ],
        },
        {
            "value": LLMProvider.MIMO.value,
            "label": "MiMo",
            "default_base_url": _MIMO_BASE_URL,
            "default_model": "mimo-v2.5-pro",
            "requires_base_url": False,
            "models": [
                {"value": "mimo-v2.5-pro", "label": "MiMo V2.5 Pro", "recommended": True},
                {"value": "mimo-v2.5", "label": "MiMo V2.5", "recommended": False},
            ],
        },
        {
            "value": LLMProvider.SILICONFLOW.value,
            "label": "硅基流动",
            "default_base_url": _SILICONFLOW_BASE_URL,
            "default_model": "Qwen/Qwen3-32B",
            "requires_base_url": False,
            "models": [
                {"value": "Qwen/Qwen3-32B", "label": "Qwen3 32B", "recommended": True},
                {"value": "deepseek-ai/DeepSeek-R1", "label": "DeepSeek R1", "recommended": False},
            ],
        },
        {
            "value": LLMProvider.CUSTOM.value,
            "label": "自定义（OpenAI 兼容）",
            # 地址与模型名都必须由用户填写：这里没有可推荐的默认值，
            # 编一个出来只会让"看起来能用、一用就 404"。
            "default_base_url": None,
            "default_model": "",
            "requires_base_url": True,
            "models": [],
        },
    ],
    "embed": [
        {
            "value": EmbedProvider.QWEN.value,
            "label": "Qwen",
            # 走 DashScope 向量端点（由 SDK 决定），不是 OpenAI 兼容接口，
            # 因此不给用户看的地址，也不接受用户覆盖。
            "default_base_url": None,
            "default_model": "text-embedding-v4",
            "requires_base_url": False,
            "models": [
                {"value": "text-embedding-v4", "label": "Text Embedding V4", "recommended": True},
            ],
        },
        {
            "value": EmbedProvider.ZHIPU.value,
            "label": "智谱 GLM",
            "default_base_url": _ZHIPU_BASE_URL,
            "default_model": "embedding-3",
            "requires_base_url": False,
            "models": [
                {"value": "embedding-3", "label": "Embedding-3", "recommended": True},
            ],
        },
        {
            "value": EmbedProvider.SILICONFLOW.value,
            "label": "硅基流动",
            "default_base_url": _SILICONFLOW_BASE_URL,
            "default_model": "BAAI/bge-m3",
            "requires_base_url": False,
            "models": [
                {"value": "BAAI/bge-m3", "label": "BGE-M3", "recommended": True},
            ],
        },
        {
            "value": EmbedProvider.CUSTOM.value,
            "label": "自定义（OpenAI 兼容）",
            "default_base_url": None,
            "default_model": "",
            "requires_base_url": True,
            "models": [],
        },
    ],
    "rerank": [
        {
            "value": RerankProvider.QWEN.value,
            "label": "Qwen",
            # DashScope 重排是专属端点（`/api/v1/services/rerank/text-rerank/text-rerank`），
            # 请求体形状与 Cohere/Jina 风格的 `/rerank` 不同，地址固定写在 retrieval.py 里。
            "default_base_url": None,
            "default_model": "gte-rerank-v2",
            "requires_base_url": False,
            "models": [
                {"value": "gte-rerank-v2", "label": "GTE Rerank V2", "recommended": True},
            ],
        },
        {
            "value": RerankProvider.ZHIPU.value,
            "label": "智谱 GLM",
            "default_base_url": _ZHIPU_BASE_URL,
            "default_model": "rerank",
            "requires_base_url": False,
            "models": [
                {"value": "rerank", "label": "GLM Rerank", "recommended": True},
            ],
        },
        {
            "value": RerankProvider.SILICONFLOW.value,
            "label": "硅基流动",
            "default_base_url": _SILICONFLOW_BASE_URL,
            "default_model": "BAAI/bge-reranker-v2-m3",
            "requires_base_url": False,
            "models": [
                {
                    "value": "BAAI/bge-reranker-v2-m3",
                    "label": "BGE Reranker V2 M3",
                    "recommended": True,
                },
            ],
        },
        {
            "value": RerankProvider.CUSTOM.value,
            "label": "自定义（OpenAI 兼容）",
            "default_base_url": None,
            "default_model": "",
            "requires_base_url": True,
            "models": [],
        },
    ],
}


def _copy_option(option: ProviderOption) -> ProviderOption:
    """复制目录项，**连同 `models` 里的每个 dict 一起**。

    只写 `dict(option)` 是浅拷贝：`models` 列表仍与全局目录共享同一个对象，
    调用方（前端序列化前的裁剪、路由层组装响应）一旦就地增删，
    改的就是全局目录本身——下一次请求返回的就不再是这里写的预设了。
    """
    return {**option, "models": [dict(model) for model in option["models"]]}


def get_catalog() -> dict[str, list[ProviderOption]]:
    """返回完整 provider 目录，供接口层直接序列化。

    返回副本而不是内部对象：调用方拿到后可能按前端需要裁剪字段，
    不能让它们改到全局目录。
    """
    return {kind: [_copy_option(option) for option in options] for kind, options in _PROVIDER_CATALOG.items()}


def default_for(kind: str, provider: str) -> ProviderOption | None:
    """按类别与 provider 取值查出目录项。找不到返回 None。"""
    for option in _PROVIDER_CATALOG.get(kind, []):
        if option["value"] == provider:
            return _copy_option(option)
    return None


def supported_values(kind: str) -> set[str]:
    """返回某类别下所有合法 provider 取值，用于请求校验。"""
    return {option["value"] for option in _PROVIDER_CATALOG.get(kind, [])}


def preset_models(kind: str, provider: str) -> list[ModelOption]:
    """返回某 provider 的预设模型列表（副本）。custom 返回空列表。"""
    option = default_for(kind, provider)
    return [dict(model) for model in option["models"]] if option else []


def requires_explicit_base_url(kind: str, provider: str) -> bool:
    """该 provider 的接口地址是否必须由用户填写。

    判据取自目录项的 `requires_base_url`，**不是**"`default_base_url` 是否为空"：
    Embedding / Reranker 的 qwen 也没有可展示的地址，但它的端点由代码固定，
    用户既不需要也不能填——用后者判断会让界面平白多出一个填了也不生效的输入框。
    """
    option = default_for(kind, provider)
    return bool(option and option["requires_base_url"])


def resolve_base_url(kind: str, provider: str, saved_base_url: str | None) -> str | None:
    """按「已保存的地址优先、目录默认地址兜底」解析实际要用的接口地址。

    集中成一处是因为这条规则被四个地方用到（配置响应的组装、连接测试取已保存地址、
    查询期构造 Embedding、重排构造），各写一遍迟早会出现"某一条路径忘了兜底"。

    两者都没有时返回 `None`，**不在这里抛错**：对 qwen 的向量/重排来说
    "没有地址"是正常状态（端点由代码固定），只有构造层才知道该地址是否必需。
    """
    option = default_for(kind, provider)
    return (saved_base_url or "").strip() or (option["default_base_url"] if option else None)
