"""provider 目录：各 provider 的默认地址，以及地址是否必须由用户填写。

设计意图：**前端不硬编码 provider**。`README.md` 第 3.2 节特别提醒
「模型供应商会更新模型名和推荐版本，前端 provider 列表由后端配置返回」，
因此这里集中维护一份目录，由 `GET /api/config/providers` 暴露给前端，
将来新增 provider 或调整默认地址只改这一个文件。

**本系统只支持远程 Provider**：本地模型方案已于 2026-10-02 整体移除（本地权重加载、
进程级缓存、`local` 取值与环境变量路径一并删除），因此每个 provider 都需要 API Key，
这里也不再需要"该 provider 是否需要 Key"这类判断。

## 目录里没有模型名（2026-10-04 改）

模型名**一律由用户填写**，目录不提供任何模型名，代码里也不保留任何内置兜底值。
以前这里有一份 `models`（预设列表，给 `<datalist>` 做建议下拉）和一个
`default_model`（切 provider 时自动填入输入框），加上调用层若干 `model or "..."` 的
静默兜底，共同造成一种状态：**用户不知道自己实际在用哪个模型**——
界面上显示一个、库里存一个、真正发出去的可能是第三个（其中还有已退场的旧名），
而 token 成本与回答质量都由用户承担。这几处已在 2026-10-04 全部删除：

- 目录不再返回模型名，界面因此没有可填入、可提示的名字；
- 模型名为空时**直接报错**（`build_embedding` / `score_with_reranker` /
  `_build_llm` 各自校验），不再换成别的模型继续跑。

需要"给用户建议"时应当明确做成产品功能（例如可选的自绘候选面板），
而不是藏在兜底逻辑里。

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

## 地址来源（2026-10-04 复核）

智谱 `https://open.bigmodel.cn/api/paas/v4`、硅基流动 `https://api.siliconflow.cn/v1`
按各家官方文档核对；MiMo 的 `https://api.xiaomimimo.com/v1` 来自其官方开放平台说明；
DeepSeek 的 `https://api.deepseek.com` 为其 OpenAI 兼容端点。
模型名方面只保留一条**历史说明**（不再作为默认值）：`deepseek-chat` /
`deepseek-reasoner` 已于 2026-07-24 下线，`deepseek-v4-flash` / `deepseek-v4-pro`
也已退场，官方当前要求填 `deepseek-flash`——这些都需要用户自己确认后填写。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

# 三类 provider 里都存在的"自定义端点"取值：目录里没有默认地址，
# 地址与模型名全部由用户填写。用常量而不是散落的字面量，避免各处拼错后静默走错分支。
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


class ProviderOption(TypedDict):
    """单个 provider 的可选项描述。"""

    value: str
    label: str
    # None 表示"没有可直接使用的默认地址"：或由代码固定（qwen 的向量/重排），
    # 或必须由用户填写（custom）。见模块文档的三种情况。
    default_base_url: str | None
    # 该 provider 的地址是否**必须由用户填写**（当前只有 custom 为 True）。
    # 放进目录而不是让前端判断 provider 名：前端不硬编码 provider（README 3.2），
    # 由后端把"要不要显示地址输入框"这件事作为数据告诉它。
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


# provider 默认地址表。**注意这里不含模型名**：模型名由用户填写。
_PROVIDER_CATALOG: dict[str, list[ProviderOption]] = {
    "llm": [
        {
            "value": LLMProvider.DEEPSEEK.value,
            "label": "DeepSeek",
            "default_base_url": _DEEPSEEK_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": LLMProvider.QWEN.value,
            "label": "Qwen",
            "default_base_url": _QWEN_COMPATIBLE_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": LLMProvider.ZHIPU.value,
            "label": "智谱 GLM",
            "default_base_url": _ZHIPU_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": LLMProvider.MIMO.value,
            "label": "MiMo",
            "default_base_url": _MIMO_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": LLMProvider.SILICONFLOW.value,
            "label": "硅基流动",
            "default_base_url": _SILICONFLOW_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": LLMProvider.CUSTOM.value,
            "label": "自定义（OpenAI 兼容）",
            # 地址与模型名都必须由用户填写：这里没有可推荐的默认地址，
            # 编一个出来只会让"看起来能用、一用就 404"。
            "default_base_url": None,
            "requires_base_url": True,
        },
    ],
    "embed": [
        {
            "value": EmbedProvider.QWEN.value,
            "label": "Qwen",
            # 走 DashScope 向量端点（由 SDK 决定），不是 OpenAI 兼容接口，
            # 因此不给用户看的地址，也不接受用户覆盖。
            "default_base_url": None,
            "requires_base_url": False,
        },
        {
            "value": EmbedProvider.ZHIPU.value,
            "label": "智谱 GLM",
            "default_base_url": _ZHIPU_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": EmbedProvider.SILICONFLOW.value,
            "label": "硅基流动",
            "default_base_url": _SILICONFLOW_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": EmbedProvider.CUSTOM.value,
            "label": "自定义（OpenAI 兼容）",
            "default_base_url": None,
            "requires_base_url": True,
        },
    ],
    "rerank": [
        {
            "value": RerankProvider.QWEN.value,
            "label": "Qwen",
            # DashScope 重排是专属端点（`/api/v1/services/rerank/text-rerank/text-rerank`），
            # 请求体形状与 Cohere/Jina 风格的 `/rerank` 不同，地址固定写在 retrieval.py 里。
            "default_base_url": None,
            "requires_base_url": False,
        },
        {
            "value": RerankProvider.ZHIPU.value,
            "label": "智谱 GLM",
            "default_base_url": _ZHIPU_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": RerankProvider.SILICONFLOW.value,
            "label": "硅基流动",
            "default_base_url": _SILICONFLOW_BASE_URL,
            "requires_base_url": False,
        },
        {
            "value": RerankProvider.CUSTOM.value,
            "label": "自定义（OpenAI 兼容）",
            "default_base_url": None,
            "requires_base_url": True,
        },
    ],
}


def _copy_option(option: ProviderOption) -> ProviderOption:
    """返回目录项的副本。

    目录项现在的所有取值都是不可变的（str / bool / None），浅拷贝就够；
    仍然复制是因为调用方（路由层组装响应）可能按前端需要裁剪字段，
    不能让它们改到全局目录本身。
    """
    return dict(option)  # type: ignore[return-value]


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
