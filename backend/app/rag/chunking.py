"""切块策略。

遵守 `docs/CODING_CONVENTIONS.md` 第 10.1 节：每个 chunk 的 metadata
必须包含 user_id、document_id、filename、chunk_id、index_version。

用 LlamaIndex 的 `SentenceSplitter` 而不是固定长度硬切：
它在标点与句子边界处断开，能显著减少「一句话被切成两半」导致的语义碎片，
对中文知识库的检索质量影响很明显。

metadata **不进 Chroma 的向量文本**，而是作为独立的 metadata 字段存储，
这样既不影响向量语义，又能在检索时用于过滤与引用来源展示。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

# chunk_id 前缀，形如 doc{id}_chunk{序号:03d}
_CHUNK_ID_PREFIX = "doc"
_CHUNK_INDEX_WIDTH = 3


@dataclass
class Chunk:
    """一个切块及其 metadata。"""

    chunk_id: str
    text: str
    metadata: dict[str, object]


def build_chunk_id(document_id: int, index: int) -> str:
    """构造稳定且可读的 chunk_id。

    序号补零到 3 位，确保按字符串排序时顺序与自然顺序一致
    （否则 chunk10 会排在 chunk2 前面），便于人工排查与按序展示。
    """
    return f"{_CHUNK_ID_PREFIX}{document_id}_chunk{index:0{_CHUNK_INDEX_WIDTH}d}"


def text_fingerprint(text: str) -> str:
    """计算文本指纹，用于判断文档内容是否真的变化。

    只看 sha256 就够：sha256 已经能识别内容变化，指纹只是用于日志与调试时
    更短的标识，避免把整段文本打进日志。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def split_text(
    text: str,
    *,
    document_id: int,
    user_id: int,
    filename: str,
    index_version: int,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """把文本切成带 metadata 的块。"""
    # 延迟导入：llama_index 的导入开销较大（约 1 秒），
    # 放在函数内可以让不需要切块的接口（如索引状态查询）不必为此付出代价。
    from llama_index.core.node_parser import SentenceSplitter

    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # 中文没有空格分词，默认的分隔符集合以英文标点为主，
        # 这里显式补上中文标点，否则整段中文会因为没有分隔符而无法切开。
        paragraph_separator="\n\n\n",
        secondary_chunking_regex="[^。！？；\n]+[。！？；\n]?",
    )

    pieces = splitter.split_text(text)
    chunks: list[Chunk] = []
    for index, piece in enumerate(pieces):
        content = piece.strip()
        if not content:
            # 空白块如果写进向量库，会在检索时命中一堆无意义内容。
            continue
        chunk_id = build_chunk_id(document_id, index)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=content,
                metadata={
                    "user_id": user_id,
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_id": chunk_id,
                    "index_version": index_version,
                },
            )
        )

    logger.info(
        "切块完成 document_id=%s chunks=%d chunk_size=%d overlap=%d",
        document_id,
        len(chunks),
        chunk_size,
        chunk_overlap,
    )
    return chunks
