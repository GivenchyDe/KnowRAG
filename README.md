# KnowRAG · RAG个人知识库问答系统

> 前端 Vue3 · 多用户登录 · 多模型可选 · 本地/远程模型混合 · 会话严格隔离

> 说明：README 负责项目总览和关键架构说明；具体编码、目录、数据库字段、接口契约和阶段验收以 `docs/DESIGN_IMPLEMENTATION.md` 为准。

---

## 一、需求确认

| 编号 | 需求                                                   | 设计要点                                     |
| ---- | ------------------------------------------------------ | -------------------------------------------- |
| 1    | 前端 Vue3                                              | Vue3 + Vite + Pinia + Vue Router + UI 组件库 |
| 2    | 登录系统，隔绝用户会话污染                             | 用户级 session_id + 用户级配置隔离           |
| 3    | LLM 可选 DeepSeek / Qwen，用户自配 API Key             | 用户级配置表 + 模型工厂                      |
| 4    | Embedding 本地 bge-m3，也可选 Qwen Embedding           | 双模式：local / remote                       |
| 5    | Reranker 本地 bge-reranker-large，也可选 Qwen Reranker | 双模式：local / remote                       |

**生产级目标补充**：

- 支持用户、会话、文档、索引、配置的严格隔离，避免不同用户或不同会话互相污染。
- 支持模型配置变更后的索引版本管理，避免不同 Embedding 模型生成的向量混用。
- 支持异步文档摄取、任务状态追踪、失败重试，避免上传大文件时阻塞请求。
- 支持检索质量评测、回答引用评测、延迟与成本监控，让项目不仅“能跑”，还可衡量、可优化。
- 支持 Docker Compose 一键部署，并明确开发环境与生产环境的差异。

---

## 二、整体架构（更新版）

```text
┌──────────────────────────────────────────────────────────────┐
│                    前端 Vue3 SPA                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐    │
│  │ 登录页    │ │ 聊天页    │ │ 文档管理  │ │ 模型配置页    │    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘    │
│  Pinia 状态管理 / Vue Router / Axios / SSE 流式解析           │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP + SSE
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI 后端                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ auth 路由   │ │ docs 路由   │ │ chat 路由   │ │ config 路由│ │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬─────┘ │
│        │              │              │              │       │
│  ┌─────▼──────────────▼──────────────▼──────────────▼─────┐ │
│  │  依赖注入 / JWT 认证 / 用户上下文 / 限流 / 审计日志        │ │
│  └──────────────────────────┬─────────────────────────────┘ │
└─────────────────────────────┼───────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                   RAGApplication（用户级实例）                │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ 异步摄取    │ │ 会话记忆    │ │ 混合检索    │ │ 重排序    │ │
│  └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
│  索引版本管理 / Prompt Injection 防护 / 引用来源生成          │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                      ModelFactory 模型工厂                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ LLM Provider │ │ Embed Provider│ │ Rerank Provider      │ │
│  │ deepseek     │ │ local bge-m3 │ │ local bge-reranker   │ │
│  │ qwen         │ │ qwen embed   │ │ qwen rerank          │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                        存储层                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ PostgreSQL │ │ Chroma     │ │ docstore   │ │ task_store│ │
│  │ 用户/配置   │ │ 向量库     │ │ 文档/索引   │ │ 聊天/任务  │ │
│  └────────────┘ └────────────┘ └────────────┘ └───────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 三、关键设计

### 3.1 用户登录与会话隔离

**问题**：之前用 `current_user.username` 作为 `session_id`，同一用户多标签共享记忆，多用户之间靠 username 区分，不够严格。

**新设计**：

```text
session_id = f"{user_id}:{conversation_id}"
```

- `user_id`：用户唯一标识（数据库主键）。
- `conversation_id`：前端生成的 UUID，每个会话独立。
- 前端切换会话时生成新 `conversation_id`。

**隔离层次**：

| 层次     | 隔离方式                                      |
| -------- | --------------------------------------------- |
| 聊天记忆 | `memories[user_id][conversation_id]`          |
| 聊天历史 | `chat_store` 按 `session_id` 分 key           |
| 用户配置 | 数据库按 `user_id` 存                         |
| 向量库   | 按 `user_id` 分 collection 或按 metadata 过滤 |
| 文档     | 按 `user_id` 分目录                           |

**推荐**：向量库按用户分 collection：

```python
collection_name = f"user_{user_id}_kb"
```

或单 collection + metadata 过滤：

```python
metadata={"user_id": user_id}
```

前者隔离更彻底，后者更省资源。个人系统推荐**按用户分 collection**。

---

### 3.2 用户配置表设计

用户自行配置 API Key 和模型，需要持久化。

**表：`user_model_configs`**

| 字段                | 类型     | 说明                                      |
| ------------------- | -------- | ----------------------------------------- |
| `id`                | INTEGER  | 主键                                      |
| `user_id`           | INTEGER  | 外键，唯一关联用户                        |
| `llm_provider`      | VARCHAR  | `deepseek` / `qwen`                       |
| `llm_api_key_encrypted` | TEXT | 加密后的 LLM API Key                      |
| `llm_base_url`      | VARCHAR  | 可选，默认官方 OpenAI-compatible endpoint |
| `llm_model`         | VARCHAR  | 如 `deepseek-chat` / `qwen-plus`          |
| `llm_temperature`   | FLOAT    | 默认 0.1                                  |
| `llm_max_tokens`    | INTEGER  | 默认 2048                                 |
| `embed_provider`    | VARCHAR  | `local` / `qwen`                          |
| `embed_model_path`  | VARCHAR  | 本地路径，仅 local                        |
| `embed_api_key_encrypted` | TEXT | 加密后的远程 Embedding API Key            |
| `embed_model`       | VARCHAR  | 如 `BAAI/bge-m3` / `text-embedding-v4`    |
| `embed_dimension`   | INTEGER  | 当前 Embedding 维度，用于索引兼容校验     |
| `rerank_provider`   | VARCHAR  | `local` / `qwen`                          |
| `rerank_model_path` | VARCHAR  | 本地路径，仅 local                        |
| `rerank_api_key_encrypted` | TEXT | 加密后的远程 Reranker API Key             |
| `rerank_model`      | VARCHAR  | 如 `bge-reranker-large` / `gte-rerank-v2` |
| `updated_at`        | DATETIME | 更新时间                                  |

**安全**：

- API Key 用对称加密（如 Fernet）存储。
- 接口返回时脱敏：`sk-****xxxx`。
- 日志中禁止打印完整 Key。
- API Key 支持删除、替换、测试连通性，不在前端二次展示明文。

**模型选择建议**：

| 类型      | 推荐默认值                         | 说明                                               |
| --------- | ---------------------------------- | -------------------------------------------------- |
| LLM       | DeepSeek / Qwen 作为可切换 provider | 不把“最新模型名”写死在代码里，通过配置中心维护     |
| Embedding | 本地 `BAAI/bge-m3`                  | 中文/英文/多语言表现好，适合作为个人知识库本地默认 |
| Embedding | 远程 `text-embedding-v4`            | 适合部署环境不方便加载本地模型时使用               |
| Reranker  | 本地 `bge-reranker-large`           | 检索候选重排，提高引用片段相关性                   |
| Reranker  | 远程 `gte-rerank-v2`                | 远程重排兜底，减少本地 GPU/内存压力                |

> 注意：模型供应商会更新模型名和推荐版本。代码里只保留稳定 fallback，前端 provider 列表由后端配置返回，便于后续替换模型而不改业务代码。

---

### 3.3 模型工厂设计

不再使用全局 `Settings.llm`，改为**按用户配置动态创建**。

```python
class ModelFactory:
    @staticmethod
    def create_llm(config: UserModelConfig):
        if config.llm_provider == "deepseek":
            return DeepSeekLLM(
                api_key=decrypt_api_key(config.llm_api_key_encrypted),
                api_base=config.llm_base_url or "https://api.deepseek.com",
                model=config.llm_model or "deepseek-chat",
                temperature=config.llm_temperature,
            )
        elif config.llm_provider == "qwen":
            return DashScope(
                api_key=decrypt_api_key(config.llm_api_key_encrypted),
                api_base=config.llm_base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                model_name=config.llm_model or "qwen-plus",
                temperature=config.llm_temperature,
            )
        raise ValueError(f"Unsupported LLM provider: {config.llm_provider}")

    @staticmethod
    def create_embedding(config: UserModelConfig):
        if config.embed_provider == "local":
            return HuggingFaceEmbedding(
                model_name=config.embed_model_path
                or r"E:\Agent\develop\Local_model\models\BAAI--bge-m3",
            )
        elif config.embed_provider == "qwen":
            return DashScopeEmbedding(
                api_key=decrypt_api_key(config.embed_api_key_encrypted),
                model_name=config.embed_model or "text-embedding-v4",
            )
        raise ValueError(f"Unsupported Embed provider: {config.embed_provider}")

    @staticmethod
    def create_reranker(config: UserModelConfig):
        if config.rerank_provider == "local":
            return SentenceTransformerRerank(
                model=config.rerank_model_path
                or r"E:\Agent\develop\Local_model\models\BAAI--bge-reranker-large",
                top_n=5,
            )
        elif config.rerank_provider == "qwen":
            return DashScopeRerank(
                api_key=decrypt_api_key(config.rerank_api_key_encrypted),
                model=config.rerank_model or "gte-rerank-v2",
                top_n=5,
            )
        raise ValueError(f"Unsupported Rerank provider: {config.rerank_provider}")
```

**关键点**：

- 用户配置从哪里来 → 数据库。
- 每次请求前根据 `user_id` 加载配置。
- 模型实例可以按 `user_id` 缓存，配置变更时失效。
- Embedding 配置变更必须触发索引兼容性检查，不允许新旧向量混用。

---

### 3.4 用户级 RAGApplication 管理

之前 `get_rag_service` 是全局单例。现在每个用户配置不同，需要**用户级实例**。

```python
_user_apps: Dict[int, RAGApplication] = {}
_apps_lock = threading.Lock()

def get_user_rag_app(user_id: int) -> RAGApplication:
    if user_id not in _user_apps:
        with _apps_lock:
            if user_id not in _user_apps:
                config = load_user_config(user_id)
                _user_apps[user_id] = RAGApplication(user_id, config)
    return _user_apps[user_id]
```

**缓存失效**：

- 用户修改模型配置时，删除 `_user_apps[user_id]`，下次重建。
- 用户上传新文档时，清空该用户的 `rag_retriever` 缓存。

**内存控制**：

- 如果用户很多，`_user_apps` 会占内存。
- 可以用 LRU 缓存，或只缓存活跃用户。
- 个人系统用户少，直接字典即可。

---

### 3.5 本地模型路径

```python
LOCAL_BGE_M3 = r"E:\Agent\develop\Local_model\models\BAAI--bge-m3"
LOCAL_BGE_RERANKER = r"E:\Agent\develop\Local_model\models\BAAI--bge-reranker-large"
```

**加载策略**：

- 本地模型加载慢、占内存，建议**全局只加载一次**，所有用户共享。
- 远程模型按用户配置创建，轻量。

```python
_local_embed = None
_local_reranker = None

def get_local_embedding():
    global _local_embed
    if _local_embed is None:
        _local_embed = HuggingFaceEmbedding(model_name=LOCAL_BGE_M3)
    return _local_embed

def get_local_reranker():
    global _local_reranker
    if _local_reranker is None:
        _local_reranker = SentenceTransformerRerank(
            model=LOCAL_BGE_RERANKER, top_n=5
        )
    return _local_reranker
```

这样：

- 本地模型：全局一份，共享。
- 远程模型：按用户配置创建。

---

### 3.6 知识库索引版本管理

Embedding 模型一旦变化，旧索引不能直接复用。不同 Embedding 模型的向量维度、语义空间、归一化方式可能不同，混用会导致检索质量下降，甚至向量库查询失败。

**表：`knowledge_base_indexes`**

| 字段                | 类型     | 说明                                      |
| ------------------- | -------- | ----------------------------------------- |
| `id`                | INTEGER  | 主键                                      |
| `user_id`           | INTEGER  | 所属用户                                  |
| `collection_name`   | VARCHAR  | Chroma collection 名称                    |
| `embedding_provider`| VARCHAR  | `local` / `qwen`                          |
| `embedding_model`   | VARCHAR  | 当前索引使用的 Embedding 模型             |
| `embedding_dimension`| INTEGER | 向量维度                                  |
| `chunk_size`        | INTEGER  | 切块大小                                  |
| `chunk_overlap`     | INTEGER  | 切块重叠                                  |
| `index_version`     | INTEGER  | 索引版本号                                |
| `status`            | VARCHAR  | `ready` / `building` / `failed` / `stale` |
| `created_at`        | DATETIME | 创建时间                                  |
| `updated_at`        | DATETIME | 更新时间                                  |

**规则**：

- 用户修改 Embedding provider、模型名、维度、切块策略时，将旧索引标记为 `stale`。
- `stale` 索引不参与问答，前端提示用户“需要重建知识库索引”。
- 重建索引时创建新 `index_version`，构建成功后再切换为 `ready`。
- Reranker 模型变更不需要重建向量索引，只需要失效检索器缓存。

---

### 3.7 文档异步摄取任务

文档上传、解析、切块、Embedding、写入向量库可能耗时较长，不应该在 HTTP 请求中同步完成。

**表：`ingestion_tasks`**

| 字段          | 类型     | 说明                                              |
| ------------- | -------- | ------------------------------------------------- |
| `id`          | INTEGER  | 主键                                              |
| `task_id`     | VARCHAR  | 对外展示的任务 UUID                               |
| `user_id`     | INTEGER  | 所属用户                                          |
| `document_id` | INTEGER  | 对应文档                                          |
| `status`      | VARCHAR  | `pending` / `running` / `success` / `failed`      |
| `progress`    | INTEGER  | 0-100                                             |
| `error`       | TEXT     | 失败原因                                          |
| `created_at`  | DATETIME | 创建时间                                          |
| `updated_at`  | DATETIME | 更新时间                                          |

**推荐流程**：

```text
上传文件
   ↓
保存原始文件 + 创建 ingestion_tasks 记录
   ↓
后台 Worker 解析文档、切块、Embedding、写入 Chroma
   ↓
更新任务进度
   ↓
任务成功后刷新该用户 retriever 缓存
```

个人项目初期可以先用 FastAPI `BackgroundTasks`，后续升级到 Celery / RQ / Dramatiq。

---

### 3.8 检索与问答策略

**推荐 RAG pipeline**：

```text
用户问题
   ↓
Query Rewrite / 意图判断
   ↓
混合检索：BM25 + Dense Vector
   ↓
候选合并去重
   ↓
Reranker 重排序
   ↓
上下文压缩与引用来源构造
   ↓
LLM 生成回答
   ↓
返回 answer + sources + trace_id
```

**关键参数**：

| 参数             | 建议值        | 说明                             |
| ---------------- | ------------- | -------------------------------- |
| `chunk_size`     | 500-1000 tokens | 中文知识库建议从 700 左右试起    |
| `chunk_overlap`  | 80-150 tokens | 避免跨段信息丢失                 |
| `retrieval_top_k`| 20-50         | 初检候选数量                     |
| `rerank_top_n`   | 3-8           | 最终进入 Prompt 的片段数量       |
| `temperature`    | 0.1-0.3       | 知识库问答优先稳定、少发散       |

**Prompt 约束**：

- 明确要求模型优先依据检索上下文回答。
- 检索不到可靠依据时回答“不确定”，不要编造。
- 对引用片段带上文档名、页码/段落号、chunk_id。
- 对用户文档中的指令做降权处理，避免 Prompt Injection。

---

## 四、前端 Vue3 设计

### 4.1 技术栈

| 技术                          | 用途                  |
| ----------------------------- | --------------------- |
| Vue3 + Vite                   | 框架与构建            |
| TypeScript                    | 类型安全              |
| Pinia                         | 状态管理              |
| Vue Router                    | 路由                  |
| Element Plus / Ant Design Vue | UI 组件               |
| Axios                         | HTTP 请求             |
| Fetch + ReadableStream        | SSE 流式接收          |
| Markdown-it                   | 渲染回答中的 Markdown |

### 4.2 页面结构

```text
src/
├── views/
│   ├── LoginView.vue          # 登录
│   ├── ChatView.vue           # 聊天主界面
│   ├── DocumentsView.vue      # 文档管理
│   ├── SettingsView.vue       # 模型配置
│   └── HistoryView.vue        # 历史会话
├── components/
│   ├── ChatBubble.vue         # 消息气泡
│   ├── SourceList.vue         # 引用来源
│   ├── ModelSelector.vue      # 模型切换
│   └── ConversationList.vue   # 会话列表
├── stores/
│   ├── auth.ts                # 登录状态
│   ├── chat.ts                # 聊天状态
│   └── config.ts              # 用户模型配置
├── api/
│   ├── auth.ts
│   ├── chat.ts
│   └── documents.ts
├── router/
│   └── index.ts
└── App.vue
```

### 4.3 流式接收（SSE）

```typescript
// api/chat.ts
export async function streamChat(
  req: ChatRequest,
  onEvent: (event: any) => void
) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(req),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      if (part.startsWith("data: ")) {
        const json = part.slice(6);
        onEvent(JSON.parse(json));
      }
    }
  }
}
```

### 4.4 会话隔离（前端）

```typescript
// stores/chat.ts
export const useChatStore = defineStore("chat", {
  state: () => ({
    conversationId: crypto.randomUUID(),  // 每次新建会话生成
    messages: [] as Message[],
  }),
  actions: {
    newConversation() {
      this.conversationId = crypto.randomUUID();
      this.messages = [];
    },
  },
});
```

每次请求带上：

```typescript
{
  conversation_id: chatStore.conversationId,
  query: "...",
  model: configStore.llmModel,
  ...
}
```

后端用 `f"{user_id}:{conversation_id}"` 作为真正的 `session_id`。

---

## 五、后端 API 调整

### 5.1 新增接口

| 方法   | 路径                           | 说明                     |
| ------ | ------------------------------ | ------------------------ |
| POST   | `/auth/login`                  | 登录，返回 JWT           |
| POST   | `/auth/register`               | 注册                     |
| GET    | `/auth/me`                     | 当前用户                 |
| GET    | `/api/config/model`            | 获取用户模型配置（脱敏） |
| PUT    | `/api/config/model`            | 更新用户模型配置         |
| GET    | `/api/config/providers`        | 获取支持的 provider 列表 |
| GET    | `/api/chat/conversations`      | 会话列表                 |
| POST   | `/api/chat/conversations`      | 新建会话                 |
| DELETE | `/api/chat/conversations/{id}` | 删除会话                 |
| POST   | `/api/docs/upload`             | 上传文档并创建摄取任务   |
| GET    | `/api/docs/tasks/{task_id}`    | 查询文档摄取任务状态     |
| POST   | `/api/index/rebuild`           | 重建当前用户知识库索引   |
| GET    | `/api/index/status`            | 查询当前用户索引状态     |

### 5.2 ChatRequest 调整

```python
class ChatRequest(BaseModel):
    conversation_id: str
    query: str
    knowledge_bool: bool = False
    # 以下可选，覆盖用户默认配置
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
```

后端：

```python
session_id = f"{current_user.id}:{req.conversation_id}"
```

### 5.3 模型配置接口

```python
@router.put("/api/config/model")
async def update_model_config(
    config: UserModelConfigUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    old_config = load_user_config(db, current_user.id)
    save_user_config(db, current_user.id, config)

    if embedding_changed(old_config, config):
        mark_user_index_stale(db, current_user.id)

    invalidate_user_app(current_user.id)
    return CommonResponse(status="success", message="配置已更新")
```

### 5.4 文档上传接口

```python
@router.post("/api/docs/upload")
async def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    saved_file = save_user_file(current_user.id, file)
    task = create_ingestion_task(db, current_user.id, saved_file.id)
    enqueue_ingestion_task(task.task_id)
    return {"task_id": task.task_id, "status": task.status}
```

---

## 六、目录结构（更新）

```text
KnowRAG/
├── backend/
│   ├── app/
│   │   ├── core/          # 配置、日志、错误处理
│   │   ├── db/            # SQLAlchemy session、base、初始化
│   │   ├── models/        # ORM models
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   ├── routers/       # FastAPI routers
│   │   ├── services/      # 业务服务、模型工厂、RAG 应用
│   │   ├── security/      # JWT、密码、鉴权依赖
│   │   ├── rag/           # chunking、loaders、prompts、evaluators
│   │   ├── main.py
│   │   └── worker.py
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── router/
│   │   ├── stores/
│   │   ├── types/
│   │   ├── views/
│   │   └── main.ts
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── DESIGN_IMPLEMENTATION.md
│   ├── CODING_CONVENTIONS.md
│   └── UI_DESIGN_PROMPT.md
├── docker-compose.yml
├── README.md
└── .env.example
```

完整文件级目录以 `docs/DESIGN_IMPLEMENTATION.md` 为准。

---

## 七、数据流（更新）

### 7.1 登录

```text
前端 POST /auth/login
   ↓
后端校验用户名密码
   ↓
生成 JWT access token / refresh token
   ↓
生产环境推荐写入 HttpOnly + Secure + SameSite Cookie
   ↓
后续请求自动携带 Cookie，或开发环境使用 Authorization Header
```

### 7.2 模型配置

```text
前端打开设置页
   ↓
GET /api/config/model → 返回脱敏配置
   ↓
用户修改 provider / API Key / 模型
   ↓
PUT /api/config/model
   ↓
后端加密存储到数据库
   ↓
失效该用户的 RAGApplication 缓存
```

### 7.3 上传文档

```text
前端选文件 → POST /api/docs/upload
   ↓
后端按 user_id 存到 file/users/{user_id}/documents
   ↓
保存原始文件 + 创建 ingestion_tasks 记录，立即返回 task_id
   ↓
后台 Worker 解析、切块、Embedding
   ↓
写入该用户的 Chroma collection
   ↓
更新 knowledge_base_indexes / documents / ingestion_tasks 状态
```

### 7.4 流式问答

```text
前端 POST /api/chat/stream
  请求体：{ conversation_id, query, knowledge_bool }
   ↓
后端：session_id = f"{user_id}:{conversation_id}"
   ↓
加载该用户配置 → ModelFactory 创建 LLM
   ↓
加载该用户索引和检索器
   ↓
astream_chat 流式生成
   ↓
SSE 推送 text / sources / complete
   ↓
前端逐字渲染
```

---

## 八、安全设计

| 项           | 措施                       |
| ------------ | -------------------------- |
| 密码         | bcrypt 哈希                |
| JWT          | 短期 access + 长期 refresh |
| API Key      | Fernet 对称加密存储        |
| API Key 返回 | 脱敏 `sk-****xxxx`         |
| 日志         | 禁止打印完整 Key           |
| 用户隔离     | 所有查询带 `user_id` 条件  |
| 向量库       | 按用户分 collection        |
| 文件         | 按用户分目录               |
| 权限         | `/api/index/rebuild`、`/api/config/model` 仅本人 |
| CORS         | 生产收紧白名单             |
| HTTPS        | 生产必须                   |
| Token 存储   | 生产推荐 HttpOnly Cookie   |
| Markdown 渲染 | HTML 清洗，防止 XSS       |
| 文件上传     | 限制类型、大小、文件名     |
| 路径安全     | 禁止路径穿越               |
| Prompt 注入  | 文档内容不允许覆盖系统指令 |
| 访问频率     | 登录、上传、问答接口限流   |
| 审计日志     | 记录配置变更和索引重建     |

---

## 九、评测与监控

### 9.1 RAG 质量评测

为了让项目具备简历说服力，需要构建一组固定评测集，而不是只靠人工试问。

| 指标             | 说明                                       |
| ---------------- | ------------------------------------------ |
| `Recall@K`       | 正确文档片段是否出现在前 K 个检索结果中   |
| `MRR` / `nDCG`   | 正确片段排序是否靠前                       |
| 引用命中率       | 回答引用是否真的来自相关文档               |
| 忠实性           | 回答是否基于上下文，是否出现幻觉           |
| 拒答准确率       | 文档没有答案时是否能回答“不确定”           |
| Rerank 提升      | 对比 rerank 前后的 Recall / nDCG           |

### 9.2 性能与可观测性

| 监控项       | 目标                                      |
| ------------ | ----------------------------------------- |
| 问答延迟     | 记录检索、重排、LLM 首 token、总耗时      |
| 摄取耗时     | 记录解析、切块、Embedding、写入向量库耗时 |
| Token 成本   | 按用户、模型、会话统计输入/输出 token     |
| 错误率       | 记录模型调用失败、索引失败、解析失败      |
| trace_id     | 每次问答返回 trace_id，便于日志追踪       |

---

## 十、部署方案

### 10.1 开发环境

```bash
# 后端
cd backend
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm run dev
```

Vite 配置代理：

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
    },
  },
});
```

### 10.2 生产环境

```yaml
# docker-compose.yml
version: "3.8"
services:
  backend:
    build:
      context: ./backend
      dockerfile: ../docker/Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://...
      - JWT_SECRET=...
      - FERNET_KEY=...
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8000
    volumes:
      - ./data:/app/file

  frontend:
    build:
      context: ./frontend
      dockerfile: ../docker/Dockerfile.frontend
    ports:
      - "80:80"
    depends_on:
      - backend

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=knowrag
      - POSTGRES_USER=knowrag
      - POSTGRES_PASSWORD=...
    volumes:
      - pgdata:/var/lib/postgresql/data

  chroma:
    image: chromadb/chroma:latest
    volumes:
      - chromadata:/chroma/chroma

  worker:
    build:
      context: ./backend
      dockerfile: ../docker/Dockerfile.backend
    command: python -m app.worker
    environment:
      - DATABASE_URL=postgresql://...
      - FERNET_KEY=...
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8000
    volumes:
      - ./data:/app/file
    depends_on:
      - backend
      - postgres
      - chroma

volumes:
  pgdata:
  chromadata:
```

---

## 十一、路线图（更新）

当前状态：已完成 README、设计实现文档、UI 设计提示词和代码约定文档；尚未进入工程脚手架编码阶段。

实现路线图以 `docs/DESIGN_IMPLEMENTATION.md` 的 Phase 0-6 为准：

- [ ] Phase 0：项目脚手架
- [ ] Phase 1：用户系统
- [ ] Phase 2：用户模型配置
- [ ] Phase 3：文档上传与异步摄取
- [ ] Phase 4：RAG 问答
- [ ] Phase 5：隔离、安全、质量
- [ ] Phase 6：Docker 与简历包装

---

## 十二、实现文档建议

README 负责说明项目目标、架构边界和关键技术决策；真正编码前，建议单独编写《设计实现文档》，用于拆解模块、数据表、接口、任务顺序和验收标准。

推荐文档结构：

```text
docs/DESIGN_IMPLEMENTATION.md
├── 1. 项目目标与非目标
├── 2. 当前代码现状分析
├── 3. 数据库表设计与迁移计划
├── 4. 后端模块拆分与接口契约
├── 5. RAG 摄取、索引、检索、重排、生成流程
├── 6. 前端页面、状态管理与 API 调用设计
├── 7. 安全策略与用户隔离检查清单
├── 8. 测试计划与 RAG 评测集
├── 9. Docker 部署方案
└── 10. 分阶段实现路线图
```

建议按照《设计实现文档》编码，原因是这个项目横跨前端、后端、数据库、向量库、模型调用和部署。如果直接按 README 开写，容易出现接口字段不一致、索引重建遗漏、缓存失效遗漏、安全边界不清等问题。

同时建议遵守 `docs/CODING_CONVENTIONS.md`，统一代码规范、注释规范、接口规范、日志规范和安全边界。

---

## 十三、一句话总结

> **KnowRAG** 从单用户、全局配置的 RAG 服务，升级为**多用户、Vue3 前端、用户级模型配置、本地/远程模型混合、会话严格隔离**的生产级个人知识库问答系统。

