"""检索链路：向量初检 → Reranker 精排 → 构造上下文。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 7.2 节。

**偏离设计文档**：文档里写的是「Dense + BM25 混合检索」。本阶段只实现 Dense 检索 +
Reranker，原因：BM25 需要为每份文档构建倒排索引并持久化（LlamaIndex 的
`BM25Retriever` 面向内存中的节点集合，进程重启即丢失），这属于额外的索引基础设施。
Reranker 已经承担了「把关键词层面相关的片段排到前面」的职责，先做 Dense + Rerank
能以更小成本拿到大部分收益。混合检索留作后续优化。

每个切片在写入向量库时都带了 `user_id` metadata，检索时强制过滤，
即使集合已按用户命名也保留这层过滤，形成纵深防御。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.models.model_config import ModelConfig
from app.services import vector_service

logger = get_logger(__name__)

# 初检候选数。设计文档给的范围是 20-50，取 30 与第 7.2 节示例一致。
DEFAULT_TOP_K = 30
# 最终进入 Prompt 的片段数。设计文档第 7.2 节示例为 5。
DEFAULT_TOP_N = 5

# 相关性阈值（两道，分别针对两种完全不同的分数）。
#
# 【第一道】向量初检相似度阈值：在精排前丢掉明显无关的候选，
# 既减少 Reranker 的计算量，也让日志里的初检数更有意义。
# 分数是 cosine 相似度（1 - 距离），实际取值多在 0.2~0.6。
#
# 取值必须依据实测，**不能凭直觉取 0.5**。当初用本地 bge-m3 测得的分布是：
#   相关问题 0.35 / 0.52 / 0.56
#   无关问题 0.32 / 0.35（今天天气怎么样）
# 两类分布**重叠**。若取 0.5，会把「切块大小是多少？」(0.35) 直接丢掉——
# 而它实际精排分高达 0.69，是正确命中。因此这里只取一个明显低于相关样本下沿的值，
# 用于剔除接近零的噪声；真正的相关性判断交给第二道精排阈值。
DEFAULT_VECTOR_SIMILARITY_CUTOFF = 0.15

# 【第二道】精排阈值。
#
# 为什么需要它：Reranker 对完全不相关的片段会给出接近 0 的分数。
# 实测「今天天气怎么样？」这类与知识库无关的问题时，所有候选的精排分都是 0.0。
# 如果没有阈值，这些 0 分片段会被当作「资料」送进 Prompt 并展示为引用来源，
# 结果是模型基于无关内容编答案、用户看到一堆假引用——
# 而设计文档第 10.4 节明确要求「文档没有答案时能回答不确定」。
#
# 取值说明：0.1 是当初用本地 cross-encoder 的 logit 分布标定出来的保守阈值
# （相关片段实测 0.5-0.9、不相关为 0.0 或负数）。本地模型已移除，现在只有远程
# Reranker（gte-rerank-v2 返回 0-1 的 relevance_score），这个取值**尚未在新模型上
# 重新标定**；当前保留旧值以免改变既有行为，真实阈值需要在 Phase 5 用评测集标定。
DEFAULT_RERANK_THRESHOLD = 0.1


@dataclass
class Passage:
    """一个候选片段。"""

    chunk_id: str
    text: str
    filename: str
    document_id: int
    # 向量初检的相似度（1 - cosine 距离，越大越相关）；纯 Rerank 结果时为 None
    vector_score: float | None = None
    # Reranker 打分（CrossEncoder 的原始 logit，越大越相关）
    rerank_score: float | None = None

    def to_source(self) -> dict[str, Any]:
        """转换为对外返回的引用来源。

        只暴露对用户有意义且不敏感的字段：文件名、切片 ID、分数。
        **不返回 stored_path**——那是服务端磁盘路径，泄露后可用于探测目录结构。
        """
        score = self.rerank_score if self.rerank_score is not None else self.vector_score
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "chunk_id": self.chunk_id,
            "score": round(float(score), 4) if score is not None else None,
        }


@dataclass
class RetrievalResult:
    """检索结果。"""

    query: str
    passages: list[Passage] = field(default_factory=list)
    # 初检候选数，用于日志与评测
    candidate_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.passages

    def sources(self) -> list[dict[str, Any]]:
        return [passage.to_source() for passage in self.passages]


def build_embedding(*, provider: str, model: str, api_key: str) -> Any:
    """按显式参数构造 Embedding 实例。

    为什么把构造逻辑独立出来：连接测试要验证的是**用户当前填的** provider / 模型 / Key
    （可能还没保存），因此不能只接受一个 `ModelConfig` 再从库里读凭据。
    生产路径（`_build_query_embedding`）与测试路径都调用本函数，
    保证两边"怎么造 Embedding"永远一致——否则测试通过而线上失败最难排查。
    """
    if provider == "qwen":
        from llama_index.embeddings.dashscope import DashScopeEmbedding

        if not api_key:
            raise AppError(
                ErrorCode.MODEL_CONFIG_INVALID,
                "Embedding provider 为 qwen，但未提供 Embedding API Key",
            )
        return DashScopeEmbedding(model_name=model or "text-embedding-v4", api_key=api_key)

    raise AppError(ErrorCode.MODEL_CONFIG_INVALID, f"不支持的 Embedding provider：{provider}")


def _build_query_embedding(config: ModelConfig) -> Any:
    """按当前配置构造 Embedding 实例（与摄取阶段保持同一取舍）。"""
    from app.services.crypto_service import decrypt_api_key

    api_key = (
        decrypt_api_key(config.embed_api_key_encrypted) if config.embed_api_key_encrypted else ""
    )
    return build_embedding(
        provider=config.embed_provider, model=config.embed_model, api_key=api_key
    )


def score_with_reranker(
    *,
    provider: str,
    model: str,
    api_key: str,
    query: str,
    passages: list[Passage],
) -> list[Passage] | None:
    """用显式凭据对候选打分并排序。

    返回 `None` 表示**重排没有真正执行**（远程调用失败或返回结果为空），
    由调用方决定怎么办：
    - 生产路径 `rerank_passages` 选择"降级为原顺序"，不让排序问题升级为可用性问题；
    - 连接测试则必须把 `None` 当作失败——否则"测试通过"是假的。

    这就是把"打分"与"降级策略"分开的原因：两种调用方对同一个失败要做出不同反应。
    """
    if not passages:
        return []

    if provider == "qwen":
        if not api_key:
            raise AppError(ErrorCode.MODEL_CONFIG_INVALID, "未提供 Reranker API Key")
        try:
            import httpx

            response = httpx.post(
                "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model or "gte-rerank-v2",
                    "input": {"query": query, "documents": [p.text for p in passages]},
                    "parameters": {"top_n": len(passages), "return_documents": False},
                },
                timeout=20.0,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("output", {}).get("results", [])
            ordered: list[Passage] = []
            for item in results:
                index = int(item.get("index", -1))
                if 0 <= index < len(passages):
                    passages[index].rerank_score = float(item.get("relevance_score", 0.0))
                    ordered.append(passages[index])
            if ordered:
                return ordered
        except Exception as exc:
            logger.warning("远程 Reranker 调用失败：%s", type(exc).__name__)
        return None

    raise AppError(ErrorCode.MODEL_CONFIG_INVALID, f"不支持的 Reranker provider：{provider}")


def rerank_passages(
    config: ModelConfig, query: str, passages: list[Passage], top_n: int
) -> list[Passage]:
    """用 Reranker 对候选重新排序，返回前 top_n 条。

    Reranker 不可用时**不阻断问答**：降级为向量相似度排序并记录告警。
    理由是「引用片段排序不够理想」远比「完全无法回答」可接受，
    而且模型文件缺失、显存不足这类环境问题不该让整个问答功能失效。
    """
    if not passages:
        return []

    from app.services.crypto_service import decrypt_api_key

    # 缺 Key 时降级而不是报错——**保持既有语义**：重排只是排序优化，
    # 缺了它仍能给出基于向量相似度的回答，不该把整个问答打断。
    # 注意这与 Embedding 不同：Embedding 缺 Key 会让检索链路根本无法工作，
    # 那条路径必须报错（见 build_embedding）。
    # 这里显式判断而不是靠 except 兜住异常：旧实现是 AppError 恰好落在 try 里被吞掉，
    # 属于"意外行为"，一旦 try 的边界变动就会静默改变线上表现（本次重构正是如此）。
    if config.rerank_provider == "qwen" and not config.rerank_api_key_encrypted:
        logger.warning("远程 Reranker 未配置 API Key，降级为向量相似度排序")
        return passages[:top_n]

    api_key = (
        decrypt_api_key(config.rerank_api_key_encrypted) if config.rerank_api_key_encrypted else ""
    )
    ranked = score_with_reranker(
        provider=config.rerank_provider,
        model=config.rerank_model,
        api_key=api_key,
        query=query,
        passages=passages,
    )
    if ranked is None:
        # 降级：保持传入顺序（调用方已按向量相似度排好），并截断到 top_n。
        logger.warning("Reranker 未生效，降级为向量相似度排序")
        return passages[:top_n]
    return ranked[:top_n]


def retrieve(
    *,
    query: str,
    user_id: int,
    collection_name: str,
    config: ModelConfig,
    top_k: int = DEFAULT_TOP_K,
    top_n: int = DEFAULT_TOP_N,
    vector_cutoff: float = DEFAULT_VECTOR_SIMILARITY_CUTOFF,
    rerank_threshold: float = DEFAULT_RERANK_THRESHOLD,
) -> RetrievalResult:
    """执行完整检索链路。

    两道阈值按顺序生效：
    1. `vector_cutoff` 过滤向量初检结果，丢掉明显无关的噪声（省下 Reranker 的算力）；
    2. `rerank_threshold` 过滤精排结果，这是判断「是否真的相关」的主要依据。

    全部被过滤时 `is_empty` 为 True，调用方据此走「资料不足」分支，
    而不是拿无关内容生成回答。
    """
    embedding = _build_query_embedding(config)
    query_vector = embedding.get_query_embedding(query)

    raw = vector_service.query_chunks(
        collection_name, query_embedding=query_vector, top_k=top_k, user_id=user_id
    )

    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    candidates: list[Passage] = []
    dropped_by_vector = 0
    for index, chunk_id in enumerate(ids):
        text = documents[index] if index < len(documents) else ""
        meta = metadatas[index] if index < len(metadatas) else {}
        if not text or not isinstance(meta, dict):
            # 数据不完整时跳过这一条，而不是让整次检索失败。
            # 向量库里可能出现半写入或手工修改的脏数据。
            logger.warning("检索结果缺少文本或 metadata，已跳过 chunk_id=%s", chunk_id)
            continue
        distance = distances[index] if index < len(distances) else None
        # 集合用的距离度量是 cosine，相似度 = 1 - 距离
        vector_score = (1.0 - float(distance)) if distance is not None else None

        # 第一道：向量相似度阈值。
        # 只在确实拿到分数时过滤；没有分数说明该后端不返回距离，
        # 此时不能凭 0 或 None 误杀全部结果。
        if vector_score is not None and vector_score < vector_cutoff:
            dropped_by_vector += 1
            continue

        candidates.append(
            Passage(
                chunk_id=str(chunk_id),
                text=text,
                filename=str(meta.get("filename", "未知文档")),
                document_id=int(meta.get("document_id", 0)),
                vector_score=vector_score,
            )
        )

    if dropped_by_vector:
        logger.info(
            "向量初检过滤：%d 个候选相似度低于 %.2f 被剔除（剩余 %d）",
            dropped_by_vector,
            vector_cutoff,
            len(candidates),
        )

    ranked = rerank_passages(config, query, candidates, top_n)

    # 第二道：精排阈值。只在拿到精排分时过滤：若 Reranker 不可用
    # （降级为向量相似度排序），rerank_score 为 None，此时无法判断相关性，
    # 不做过滤以免把所有结果都误杀。
    kept = [
        passage
        for passage in ranked
        if passage.rerank_score is None or passage.rerank_score >= rerank_threshold
    ]
    if len(kept) != len(ranked):
        logger.info(
            "相关性过滤：%d 个候选低于阈值 %.2f 被剔除（问题可能与知识库无关）",
            len(ranked) - len(kept),
            rerank_threshold,
        )

    logger.info(
        "检索完成 user_id=%s 初检=%d 精排后=%d 采纳=%d collection=%s",
        user_id,
        len(candidates),
        len(ranked),
        len(kept),
        collection_name,
    )
    return RetrievalResult(query=query, passages=kept, candidate_count=len(candidates))


def build_context(passages: list[Passage]) -> str:
    """把片段拼成给 LLM 的上下文。

    每段前标注编号与来源文件名，使模型能够按要求给出「依据 [1]」这类引用，
    同时方便用户对照原文核验。
    """
    blocks: list[str] = []
    for index, passage in enumerate(passages, start=1):
        blocks.append(f"[{index}] 来源：{passage.filename}\n{passage.text}")
    return "\n\n---\n\n".join(blocks)


def count_tokens_estimate(text: str) -> int:
    """估算 token 数。

    只用于日志与成本观测，因此用「字符数 / 2」这种粗略估算即可。
    真正的 token 计数需要模型对应的 tokenizer，而不同 provider 的切分规则不同，
    为一个监控指标引入 tokenizer 依赖并不划算。
    """
    return max(1, len(text) // 2)
