"""ORM 模型包。

在此统一导入所有模型，确保任何 `import app.models` 之后
`Base.metadata` 中已包含全部表定义——Alembic autogenerate 依赖这一点，
漏导入会导致迁移脚本静默漏表。
"""

from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.ingestion_task import IngestionStatus, IngestionTask
from app.models.knowledge_base_index import IndexStatus, KnowledgeBaseIndex
from app.models.message import Message, MessageRole
from app.models.model_config import ModelConfig
from app.models.user import User

__all__ = [
    "Conversation",
    "Document",
    "DocumentStatus",
    "IndexStatus",
    "IngestionStatus",
    "IngestionTask",
    "KnowledgeBaseIndex",
    "Message",
    "MessageRole",
    "ModelConfig",
    "User",
]
