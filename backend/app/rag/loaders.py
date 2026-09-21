"""文档解析：把上传的文件转成纯文本。

支持格式与 `docs/UI_DESIGN_PROMPT.md` 的文档管理页预期一致：PDF、DOCX、TXT、Markdown、CSV。
不支持的格式在**解析前**由 `SUPPORTED_EXTENSIONS` 拦下，避免先落盘再报错。

为什么不用 LlamaIndex 的 `SimpleDirectoryReader`：它按目录读取，需要把文件放进
一个临时目录再读取，多一次磁盘往返；而且各类 reader 的依赖（如 pandas）会在导入时
就加载，开销大。这里按扩展名直接分派，解析失败时的错误信息也更精确。
"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)

# 支持的扩展名 -> MIME 类型。上传接口用它做白名单校验。
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
}


class UnsupportedFileTypeError(AppError):
    """文件类型不在白名单内。"""

    def __init__(self, filename: str) -> None:
        supported = "、".join(sorted(SUPPORTED_EXTENSIONS))
        super().__init__(
            ErrorCode.VALIDATION_ERROR,
            f"不支持的文件类型：{filename}。当前支持：{supported}",
        )


class DocumentParseError(AppError):
    """文件解析失败。"""

    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(ErrorCode.INGESTION_FAILED, f"解析文档失败（{filename}）：{reason}")


def is_supported(filename: str) -> bool:
    """按扩展名判断是否支持。"""
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS


def content_type_for(filename: str) -> str | None:
    """按扩展名推断 MIME 类型。

    不直接信任客户端传来的 Content-Type：它由浏览器或攻击者决定，
    而扩展名是我们自己校验过的。
    """
    return SUPPORTED_EXTENSIONS.get(Path(filename).suffix.lower())


def _read_text_file(path: Path) -> str:
    """读取纯文本类文件。

    依次尝试 UTF-8、UTF-8-SIG（带 BOM）与 GBK：中文文档里 GBK 编码仍然常见，
    统一按 UTF-8 读会直接抛 UnicodeDecodeError，让用户以为文件损坏。
    """
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    # 全部失败时用 replace 兜底，宁可少量乱码也不要完全读不出内容。
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """提取 PDF 文本。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # 单页损坏不应让整个文档失败
                logger.warning("PDF %s 第 %d 页解析失败：%s", path.name, index, type(exc).__name__)
                text = ""
            if text.strip():
                pages.append(text)
        return "\n\n".join(pages)
    except Exception as exc:
        raise DocumentParseError(path.name, f"{type(exc).__name__}") from exc


def _read_docx(path: Path) -> str:
    """提取 DOCX 文本。"""
    try:
        import docx2txt

        return docx2txt.process(str(path)) or ""
    except Exception as exc:
        raise DocumentParseError(path.name, f"{type(exc).__name__}") from exc


def extract_text(path: Path) -> str:
    """按扩展名分派解析，返回纯文本。

    解析结果为空时视为失败：空文档继续走进 embedding 会写入无意义的向量，
    用户却看到「索引成功」，属于最糟糕的静默错误。
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(path.name)

    if suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix == ".docx":
        text = _read_docx(path)
    else:
        text = _read_text_file(path)

    if not text.strip():
        raise DocumentParseError(
            path.name,
            "未能提取到任何文本。若是扫描件 PDF，需要先做 OCR；若文件为纯图片，请改用文本格式",
        )
    return text
