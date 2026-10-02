"""模型连接测试。

三个类别（LLM / Embedding / Reranker）的测试逻辑集中在这里，原因是它们共享同一套
约定，分散写会出现"某一类忘了脱敏、忘了不透传供应商报文"这类漏洞：

1. **只回可操作提示**：供应商的原始报文可能含账号、额度、请求 ID 等细节，
   一律只写服务端日志（`docs/CODING_CONVENTIONS.md` 第 9 节），不返回前端。
2. **不吞配置错误**：`AppError`（如"未提供 Key"）原样抛出，让调用方拿到准确错误码；
   只有"外部服务/模型本身失败"才被转成通用提示——否则会把配置写错伪装成网络问题。
3. **测试走的是生产同一条构造路径**（`retrieval.build_embedding` /
   `retrieval.score_with_reranker`）。用另一套代码去"测试"，通过与否都说明不了线上能否工作。

本模块**不接触数据库**：凭据由调用方（router + config_service）解析好传进来，
这样"保存的 Key 还是临时输入的 Key""地址是否允许调用方指定"这些安全决策只有一处。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.rag import retrieval

logger = get_logger(__name__)

# 单次探测的超时。远程服务的首字延迟通常在秒级，10 秒足够区分"慢"与"不可达"。
_PROBE_TIMEOUT_SECONDS = 10.0

# Embedding 测试用的固定文本。选中文短句是因为目标场景是中文知识库，
# 且长度足够触发真实前向计算（不会走空输入捷径）。
_EMBEDDING_PROBE_TEXT = "KnowRAG 测试"

# Reranker 测试用的查询与两条候选：一条强相关、一条完全无关。
# 之所以要"一正一负"而不是只给一条：只有两条分数出现明显高低差，
# 才能证明重排**真的在按语义排序**，而不是原样返回或全给同一个分。
_RERANK_PROBE_QUERY = "KnowRAG 的 Reranker 用的是什么模型？"
_RERANK_PROBE_RELEVANT = "重排阶段会用重排模型对候选片段重新排序，以提高引用片段的相关性。"
_RERANK_PROBE_IRRELEVANT = "今天天气不错，适合出门散步。"


@dataclass(frozen=True)
class ConnectionTestOutcome:
    """测试结果。

    与 `ConnectionTestResponse` 一一对应，但不依赖 pydantic：
    本模块只表达"测出来什么"，响应组装交给路由层。
    """

    success: bool
    code: str
    message: str
    detail: dict[str, Any] | None = None


def _failure(code: ErrorCode, message: str, detail: dict[str, Any] | None = None) -> ConnectionTestOutcome:
    return ConnectionTestOutcome(success=False, code=code.value, message=message, detail=detail)


# --------------------------------------------------------------------------- #
# LLM：发一次最小对话请求
# --------------------------------------------------------------------------- #


def test_llm(*, provider: str, base_url: str, model: str, api_key: str) -> ConnectionTestOutcome:
    """对 OpenAI 兼容接口发起一次最小对话请求。

    DeepSeek 与 Qwen 都提供 `/chat/completions`，因此共用这一段代码。
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = httpx.post(url, json=body, headers=headers, timeout=_PROBE_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        logger.warning("连接测试超时 provider=%s base_url=%s", provider, base_url)
        return _failure(ErrorCode.MODEL_PROVIDER_ERROR, "连接超时，请检查网络或 base_url 是否正确")
    except httpx.HTTPError as exc:
        # 异常文本可能含内网地址、证书信息等，只记类型。
        logger.warning("连接测试失败 provider=%s error=%s", provider, type(exc).__name__)
        return _failure(ErrorCode.MODEL_PROVIDER_ERROR, "无法连接到模型服务，请检查网络与 base_url")

    if response.status_code == 200:
        return ConnectionTestOutcome(success=True, code="OK", message="连接成功，模型响应正常")

    return _failure_from_status(response.status_code, provider=provider)


def _failure_from_status(status: int, *, provider: str) -> ConnectionTestOutcome:
    """按状态码给出可操作提示；原始报文只进服务端日志。"""
    logger.warning(
        "连接测试返回非 200 provider=%s status=%s",
        provider,
        status,
    )
    if status in (401, 403):
        return _failure(ErrorCode.MODEL_CONFIG_INVALID, "API Key 无效或没有访问权限")
    if status == 404:
        return _failure(ErrorCode.MODEL_CONFIG_INVALID, "接口地址或模型名不正确，请检查 base_url 与模型名")
    if status == 429:
        return _failure(ErrorCode.RATE_LIMITED, "请求过于频繁或额度已用尽")
    return _failure(ErrorCode.MODEL_PROVIDER_ERROR, f"模型服务返回异常状态（HTTP {status}）")


# --------------------------------------------------------------------------- #
# Embedding：真的算一次向量，并核对维度
# --------------------------------------------------------------------------- #


def test_embedding(
    *, provider: str, model: str, api_key: str, base_url: str | None = None
) -> ConnectionTestOutcome:
    """生成一段固定文本的向量，确认模型真的能返回向量。

    为什么不再拿配置里的维度做判据：`embed_dimension` 已改为**后端按实测值维护**
    （见 `index_service.sync_embedding_dimension`），前端也不再提供输入框。
    于是"实测维度 ≠ 配置里的维度"意味着"还没同步"，而不是"用户配错了"；
    继续判失败，用户会面对一个自己无法修正的报错。维度照实测值返回在 `detail` 里，
    由路由层决定是否写回配置（只在测的就是当前生效的模型时才写）。

    仍然保留的判据：
    - 模型必须真的返回非空向量（返回空向量说明模型不可用，而不是"维度配置错了"）；
    - 向量必须全是有限数：`NaN` / `inf` 写进向量库后检索会静默出错，值得在这里挡下。
    """
    embedding = retrieval.build_embedding(
        provider=provider, model=model, api_key=api_key, base_url=base_url
    )

    try:
        vector = embedding.get_query_embedding(_EMBEDDING_PROBE_TEXT)
    except AppError:
        # 配置类错误（如缺少 Key）原样抛出，避免被下面的通用提示掩盖。
        raise
    except Exception as exc:
        # 鉴权失败、网络异常、模型不存在等都归到这里。堆栈进日志，前端只看到可操作提示。
        logger.exception("Embedding 测试失败 provider=%s error=%s", provider, type(exc).__name__)
        return _failure(
            ErrorCode.MODEL_PROVIDER_ERROR,
            f"Embedding 调用失败（{type(exc).__name__}）。请检查 API Key、模型名与网络",
        )

    dimension = len(vector or [])
    if dimension == 0:
        return _failure(ErrorCode.MODEL_PROVIDER_ERROR, "模型返回了空向量，请检查模型是否可用")

    if not all(math.isfinite(value) for value in vector):
        return _failure(
            ErrorCode.MODEL_PROVIDER_ERROR,
            "模型返回的向量包含非法数值（NaN / inf），无法写入向量库，请检查模型与服务商",
            detail={"dimension": dimension},
        )

    return ConnectionTestOutcome(
        success=True,
        code="OK",
        message=f"向量模型连接成功，模型返回 {dimension} 维向量",
        detail={"dimension": dimension},
    )


# --------------------------------------------------------------------------- #
# Reranker：用一正一负两条候选验证"真的在按语义排序"
# --------------------------------------------------------------------------- #


def test_reranker(
    *, provider: str, model: str, api_key: str, base_url: str | None = None
) -> ConnectionTestOutcome:
    """构造一正一负两条候选，检查重排后相关候选是否排在前面。

    判据有两层：
    1. **重排确实执行了** —— `score_with_reranker` 返回 None 表示降级
       （远程调用失败或返回结果为空），此时必须判为失败。
       生产路径遇到这种情况会静默降级，而连接测试若也静默通过，用户会以为配置没问题。
    2. **排序方向正确且分数有意义** —— 强相关候选应排在无关候选之前，且分数为正。
       只验证"没报错"是不够的：模型文件损坏时也可能返回一堆 0 分。
    """
    relevant = retrieval.Passage(
        chunk_id="probe-relevant",
        text=_RERANK_PROBE_RELEVANT,
        filename="probe",
        document_id=0,
    )
    irrelevant = retrieval.Passage(
        chunk_id="probe-irrelevant",
        text=_RERANK_PROBE_IRRELEVANT,
        filename="probe",
        document_id=0,
    )

    ranked = retrieval.score_with_reranker(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        query=_RERANK_PROBE_QUERY,
        passages=[irrelevant, relevant],
    )

    if ranked is None:
        return _failure(
            ErrorCode.MODEL_PROVIDER_ERROR,
            "重排服务调用失败，请检查 API Key、模型名与网络",
        )

    scores = {passage.chunk_id: passage.rerank_score for passage in ranked}
    top = ranked[0]
    top_score = top.rerank_score if top.rerank_score is not None else 0.0
    detail: dict[str, Any] = {
        "top_score": round(float(top_score), 4),
        "top_chunk": top.chunk_id,
        "scores": {key: (round(float(v), 4) if v is not None else None) for key, v in scores.items()},
    }

    # 先判"分数有没有意义"，再判"顺序对不对"。
    # 顺序反过来检查会更早命中"顺序不对"，但那种表述对"模型文件损坏、全给 0 分"
    # 这种真实原因毫无指向性；先看分数能让提示直接指向原因。
    if top_score <= 0:
        return _failure(
            ErrorCode.MODEL_PROVIDER_ERROR,
            "重排分数异常（相关片段得分不为正），请确认模型文件完整或改换远程重排",
            detail=detail,
        )
    if top.chunk_id != relevant.chunk_id:
        return _failure(
            ErrorCode.MODEL_PROVIDER_ERROR,
            "重排结果不符合预期：相关片段没有排在无关片段之前，请确认模型是否为重排模型",
            detail=detail,
        )

    return ConnectionTestOutcome(
        success=True, code="OK", message="重排响应正常", detail=detail
    )
