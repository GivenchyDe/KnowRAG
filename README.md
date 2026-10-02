# KnowRAG · RAG个人知识库问答系统

> 前端 Vue3 · 多用户登录 · 多模型可选（远程 DeepSeek / Qwen）· 会话严格隔离

> 说明：README 负责项目总览和关键架构说明；具体编码、目录、数据库字段、接口契约和阶段验收以 `docs/DESIGN_IMPLEMENTATION.md` 为准。

---

## 一、需求确认

| 编号 | 需求                                                   | 设计要点                                     |
| ---- | ------------------------------------------------------ | -------------------------------------------- |
| 1    | 前端 Vue3                                              | Vue3 + Vite + Pinia + Vue Router + UI 组件库 |
| 2    | 登录系统，隔绝用户会话污染                             | 用户级 session_id + 用户级配置隔离           |
| 3    | LLM 可选 DeepSeek / Qwen，用户自配 API Key 与 Base URL | 全局配置表 + 按 provider 分派                |
| 4    | Embedding 可选 Qwen Embedding（`text-embedding-v4`）   | 仅远程 provider                              |
| 5    | Reranker 可选 Qwen Reranker（`gte-rerank-v2`）         | 仅远程 provider                              |

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
│  │ deepseek     │ │ qwen embed   │ │ qwen rerank          │ │
│  │ qwen         │ │              │ │                      │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                        存储层                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ MySQL      │ │ Chroma     │ │ docstore   │ │ task_store│ │
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

**推荐**：向量库按用户分 collection，**并在集合名里带上索引版本号**。

### 实现现状（以代码为准）

集合名模板在 `backend/app/services/index_service.py`：

```python
_COLLECTION_NAME_TEMPLATE = "user_{user_id}_kb_v{version}"
```

比"按用户分 collection"更进一步：**版本号进集合名**。重建索引时写入新集合
（`user_3_kb_v2`），构建成功后切换、再删除旧集合，因此**重建过程中旧索引仍可服务**，
不会出现"重建到一半用户问不了问题"的空窗。

---

### 3.2 全局模型配置表设计

模型 API Key 与模型名需要持久化。**本表不预置任何 Key**：Key 由用户在设置页自行填写，
因此配置是**全局一份**，而不是每个用户各存一份（详见 `docs/DESIGN_IMPLEMENTATION.md` 第 4.2 节）。

**表：`model_configs`**

| 字段                | 类型     | 说明                                      |
| ------------------- | -------- | ----------------------------------------- |
| `id`                | BIGINT   | 主键                                      |
| `user_id`           | BIGINT   | 可空外键，记录最近一次修改该配置的用户    |
| `llm_provider`      | VARCHAR  | `deepseek` / `qwen`                       |
| `llm_api_key_encrypted` | TEXT | 加密后的 LLM API Key                      |
| `llm_base_url`      | VARCHAR  | 可选，默认官方 OpenAI-compatible endpoint |
| `llm_model`         | VARCHAR  | 如 `deepseek-chat` / `qwen-plus`          |
| `llm_temperature`   | FLOAT    | 默认 0.1                                  |
| `llm_max_tokens`    | INTEGER  | 默认 2048                                 |
| `embed_provider`    | VARCHAR  | `qwen`                                    |
| `embed_api_key_encrypted` | TEXT | 加密后的远程 Embedding API Key            |
| `embed_model`       | VARCHAR  | 如 `text-embedding-v4`                    |
| `embed_dimension`   | INTEGER  | 向量维度。后端按模型实测值维护，界面不提供填写入口 |
| `rerank_provider`   | VARCHAR  | `qwen`                                    |
| `rerank_api_key_encrypted` | TEXT | 加密后的远程 Reranker API Key             |
| `rerank_model`      | VARCHAR  | 如 `gte-rerank-v2`                        |
| `updated_at`        | DATETIME | 更新时间                                  |

**安全**：

- API Key 用对称加密（如 Fernet）存储。
- 接口返回时脱敏：`sk-****xxxx`。
- 日志中禁止打印完整 Key。
- API Key 支持删除、替换、测试连通性，不在前端二次展示明文。

**模型选择建议**：

| 类型      | 推荐默认值          | 说明                                         |
| --------- | ------------------- | -------------------------------------------- |
| LLM       | DeepSeek / Qwen     | 不把“最新模型名”写死在代码里，通过配置中心维护 |
| Embedding | `text-embedding-v4` | DashScope 远程 Embedding，中文/多语言表现稳定 |
| Reranker  | `gte-rerank-v2`     | DashScope 远程重排，提高引用片段相关性        |

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
        if config.embed_provider == "qwen":
            return DashScopeEmbedding(
                api_key=decrypt_api_key(config.embed_api_key_encrypted),
                model_name=config.embed_model or "text-embedding-v4",
            )
        raise ValueError(f"Unsupported Embed provider: {config.embed_provider}")

    @staticmethod
    def create_reranker(config: UserModelConfig):
        if config.rerank_provider == "qwen":
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

### 3.5 模型 Provider

**本系统仅支持远程 Embedding / Reranker Provider**（Qwen / DashScope），
不加载任何本地模型权重。

> 变更说明（2026-10-02）：早期的本地模型方案（本地 `bge-m3` / `bge-reranker-large`
> 进程内加载、`local` provider、`LOCAL_BGE_*` 环境变量与推理设备配置）已整体移除——
> 代码、数据库列与界面入口均已清理。本节原先的模型加载与进程级缓存代码示例随之删除。

---

### 3.6 知识库索引版本管理

Embedding 模型一旦变化，旧索引不能直接复用。不同 Embedding 模型的向量维度、语义空间、归一化方式可能不同，混用会导致检索质量下降，甚至向量库查询失败。

**表：`knowledge_base_indexes`**

| 字段                | 类型     | 说明                                      |
| ------------------- | -------- | ----------------------------------------- |
| `id`                | INTEGER  | 主键                                      |
| `user_id`           | INTEGER  | 所属用户                                  |
| `collection_name`   | VARCHAR  | Chroma collection 名称                    |
| `embedding_provider`| VARCHAR  | `qwen`                                    |
| `embedding_model`   | VARCHAR  | 当前索引使用的 Embedding 模型             |
| `embedding_dimension`| INTEGER | 向量维度                                  |
| `embedding_signature`| VARCHAR  | 影响向量空间的**参数指纹**（provider\|model\|dimension）|
| `chunk_size`        | INTEGER  | 切块大小                                  |
| `chunk_overlap`     | INTEGER  | 切块重叠                                  |
| `index_version`     | INTEGER  | 索引版本号（同时体现在集合名里）          |
| `status`            | VARCHAR  | `ready` / `building` / `failed` / `stale` |
| `created_at`        | DATETIME | 创建时间                                  |
| `updated_at`        | DATETIME | 更新时间                                  |

> `embedding_signature` 是**实现比设计多出来的一列**，必须存指纹而不是逐列比较：
> 指纹为 `provider|model|dimension`，三者任一变化都会改变向量空间——
> 只比较 provider 会漏判同 provider 换模型名、以及实测维度变化的情况，
> 导致旧索引被当作可用，静默返回错误检索结果。

**规则**：

- 用户修改 Embedding provider、模型名时，或后端按实测值校正向量维度时，将旧索引标记为 `stale`。
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
| `started_at`  | DATETIME | 开始时间（可空）                                  |
| `finished_at` | DATETIME | 结束时间（可空）                                  |
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

### 实现现状（以代码为准）

**没有引入 Celery / RQ / Dramatiq，也没有使用 FastAPI `BackgroundTasks`**，
而是**进程内线程池**（`backend/app/services/ingestion_service.py`）。选它的理由是
`BackgroundTasks` 依附于单次 HTTP 请求的生命周期，无法承载长任务。

代价必须知情：

- 任务**不跨进程存活**。因此 `main.py` 的 lifespan 启动时会调用
  `ingestion_service.reap_stale_tasks()`，把上次进程退出遗留的 `pending` / `running`
  任务标记为失败——否则前端会一直轮询一个永不推进的任务。
- 多副本部署时 worker 与 API 在同一进程里，**无法独立扩缩容**。
  这也是 Phase 6 尚未完成的部分：`docker-compose.yml` 里还没有 `worker` 服务
  （见 10.2），**`backend/app/worker.py` 目前并不存在**。

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

### 5.1 接口清单（与实现一致）

以代码为准（`backend/app/routers/`）：`auth.py` → `/auth`、`config.py` → `/api/config`、
`documents.py` → `/api/docs`、`index.py` → `/api/index`、`chat.py` → `/api/chat`。

| 方法   | 路径                                          | 说明                                   |
| ------ | --------------------------------------------- | -------------------------------------- |
| POST   | `/auth/register`                              | 注册（201，不自动登录）                |
| POST   | `/auth/login`                                 | 登录，返回 access + refresh token 对   |
| POST   | `/auth/refresh`                               | 刷新 token                             |
| GET    | `/auth/me`                                    | 当前用户                               |
| PATCH  | `/auth/me`                                    | 修改用户名 / 邮箱（只改请求体出现的键）|
| POST   | `/auth/me/avatar`                             | 上传头像                               |
| GET    | `/api/media/avatars/<uuid>.<ext>`             | 头像静态服务（**挂在 `/api` 之下**，见 10.3）|
| GET    | `/api/config/model`                           | 获取**全局**模型配置（脱敏）           |
| PUT    | `/api/config/model`                           | 更新全局模型配置                       |
| GET    | `/api/config/providers`                       | 获取支持的 provider 列表               |
| POST   | `/api/config/model/test`                      | 测试模型连接（当前仅支持 LLM）         |
| POST   | `/api/docs/upload`                            | 上传文档并创建摄取任务（202）          |
| GET    | `/api/docs`                                   | 文档列表                               |
| DELETE | `/api/docs/{document_id}`                     | 删除文档                               |
| GET    | `/api/docs/tasks/{task_id}`                   | 查询摄取任务状态                       |
| GET    | `/api/index/status`                           | 查询索引状态                           |
| POST   | `/api/index/rebuild`                          | 重建知识库索引                         |
| POST   | `/api/chat/conversations`                     | 新建会话                               |
| GET    | `/api/chat/conversations`                     | 会话列表（分页，`is_pinned DESC, updated_at DESC, id DESC`）|
| PATCH  | `/api/chat/conversations/{conversation_id}`   | 重命名 / 置顶（只改请求体出现的键）    |
| DELETE | `/api/chat/conversations/{conversation_id}`   | 删除会话及其消息                       |
| GET    | `/api/chat/conversations/{conversation_id}/messages` | 会话历史消息                    |
| POST   | `/api/chat/stream`                            | 流式问答（SSE）                        |
| GET    | `/health`                                     | 健康检查                               |

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

## 六、目录结构（已与实现核对）

### 6.1 实际目录结构（已与代码核对）

```text
KnowRAG/
├── backend/
│   ├── app/
│   │   ├── core/          # config.py / logging.py / errors.py
│   │   ├── db/            # base.py / session.py / init_db.py
│   │   ├── models/        # user、model_config、conversation、message、
│   │   │                  # document、ingestion_task、knowledge_base_index
│   │   ├── schemas/       # auth.py / chat.py / config.py / documents.py
│   │   ├── routers/       # auth.py / chat.py / config.py / documents.py / index.py
│   │   ├── services/      # auth、crypto、config、document、ingestion、
│   │   │                  # index、chat、model_loader、vector、provider_catalog
│   │   ├── security/      # jwt.py / password.py / dependencies.py
│   │   ├── rag/           # chunking.py / loaders.py / docstore.py /
│   │   │                  # prompts.py / retrieval.py
│   │   └── main.py
│   ├── alembic/versions/  # 6 个迁移（最新 d8f2b6a15c74 add is_pinned）
│   ├── file/              # 运行时数据：用户文档 + 头像（gitignore，需单独备份）
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/           # client / auth / chat / config / documents / health
│   │   ├── components/    # 手工组件 + 已引入 Element Plus（按需引入，见 main.ts）
│   │   ├── layouts/       # AppShell.vue
│   │   ├── router/
│   │   ├── stores/        # auth / chat / config / documents / theme / ui
│   │   ├── styles/        # global.css（design tokens）
│   │   ├── types/
│   │   ├── utils/         # markdown.ts（含 DOMPurify 清洗）
│   │   ├── views/         # Login / Register / Chat / Documents / Settings / History
│   │   └── main.ts
│   ├── public/            # logo 等静态资源（构建时整目录拷进 dist）
│   ├── scripts/           # prepare_logo.py / extract_bubble_logo.py
│   ├── .env.development / .env.production
│   ├── index.html / vite.config.ts / tsconfig.json
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── DESIGN_IMPLEMENTATION.md   # 编码与接口契约的唯一权威
│   ├── CODING_CONVENTIONS.md
│   ├── UI_DESIGN_PROMPT.md
│   └── HANDOVER_*.md              # 交接文档统一放在此处
├── docker-compose.yml
├── README.md
└── .env.example
```

### 6.2 三处与旧版本文档的差异（**Phase 6 的真实起点**）

旧版 README 的目录树列了三个**实际不存在**的路径，它们正是把 Phase 6 显得"快做完了"
的原因，务必按现状理解：

| 旧文档所写 | 实际情况 |
| --- | --- |
| `backend/app/worker.py` | **不存在**。摄取任务跑在 API 进程的线程池里（见 3.7），没有独立 worker 进程 |
| `backend/tests/` | **不存在**。后端**没有任何** pytest 配置（无 `pyproject.toml` / `pytest.ini` / `conftest.py`） |
| `docker/Dockerfile.backend`、`docker/Dockerfile.frontend` | **`docker/` 目录不存在**。Dockerfile 实际在 `backend/Dockerfile` 与 `frontend/Dockerfile` |

另外 `backend/app/rag/` 下**没有** `evaluators.py`——评测脚本尚未编写（Phase 5）。
前端也**没有**任何测试框架（`package.json` 只有 `dev` / `build` / `preview` / `typecheck`）。

完整文件级目录仍以 `docs/DESIGN_IMPLEMENTATION.md` 为准；
README 与实现冲突时，**以代码为准，并回来修正本文件**。

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

**实现状态（上表是设计目标，逐项核对代码后的实际情况）**：

- **已实现**：bcrypt 密码哈希、JWT access + refresh、Fernet 加密存储 API Key、
  返回脱敏、所有查询带 `user_id` 条件、向量库按用户分 collection（且集合名带索引版本）、
  文件按用户分目录、CORS 白名单（非 `*`）、Markdown 经 DOMPurify 清洗、
  上传类型/大小/文件名限制、路径穿越防护、Prompt Injection 约束（`app/rag/prompts.py`）。
- **未实现**：`/api/index/rebuild`、`/api/config/model` 的**限流**；**审计日志**；
  **CSRF 防护**——token 实际存在 localStorage（设计建议的 HttpOnly Cookie 未采用），
  因此 CSRF 是必须补的配套项。
- **部署时生效**：HTTPS；生产环境会自动关闭 `/docs`、`/redoc`、`/openapi.json`。

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
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
```

> **通用规则**：前端要访问的任何新后端路径，都必须落在上面这三个前缀之下
> （或同步修改此配置）。顶层路径（如 `/media`）不在代理列表里时，Vite 会用自己的
> SPA fallback 返回 **200 + `index.html`**——网络面板显示"成功"，而 `<img>` 拿到的是 HTML，
> 表现为"后端日志 200、Toast 提示已保存，但图片死活不显示"。头像静态服务因此挂在
> `/api/media` 之下。

### 10.2 生产环境（**尚未完成 —— Phase 6 的起点**）

> 说明：本地开发与生产部署统一使用 **MySQL 8.0**（原设计的 PostgreSQL 已废弃，原因见 `backend/app/core/config.py` 注释）。

**仓库里现有的 `docker-compose.yml` 只编排了 3 个服务**，且它自己的注释就写明了缺口：

```yaml
# docker-compose.yml（现状摘要，非完整内容）
services:
  backend:     # build: context ./backend, dockerfile: Dockerfile
               # 端口 8000:8000；env_file .env
               # 覆盖 DATABASE_URL → mysql 服务；CHROMA_HOST=chroma / CHROMA_PORT=8000
               # depends_on: mysql（condition: service_healthy）
  mysql:       # image mysql:8.0，固定 utf8mb4 / utf8mb4_0900_ai_ci，含 healthcheck
  frontend:    # build: context ./frontend, dockerfile: Dockerfile
               # 端口 5173:80（仍按开发习惯映射，Phase 6 再改 80:80 + Nginx）
volumes:
  mysqldata:
```

**Phase 6 待补清单（按依赖顺序）**：

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | 补 `chroma` 服务 | backend 已设 `CHROMA_HOST=chroma`，但编排里**没有 chroma 服务**，所以当前这份 compose **跑不通 RAG 链路**（只能用自由对话） |
| 2 | 决定 worker 形态 | 现状是 API 进程内线程池（见 3.7）。要么保持现状并**删掉**"独立 worker"的设想，要么真的把摄取拆成独立进程——**后者需要先新建 `app/worker.py`（目前不存在）** |
| 3 | `frontend` 改 `80:80` + Nginx 反代 | 记得把 `/api`（含 `/api/media`）、`/auth`、`/health` 一并转发 |
| 4 | 数据持久化与备份 | `backend/file/` 已被 gitignore（用户文档 + 头像），**不在 git 里，需要单独备份**；compose 里应把 `./data:/app/file` 挂上 |
| 5 | 生产环境变量 | `JWT_SECRET`、`FERNET_KEY` 必须替换（后端在密钥过弱时会显式告警）；生产环境已自动关闭 `/docs`、`/redoc`、`/openapi.json` |
| 6 | CORS 收紧 | `cors_origins` 走白名单（已实现，非 `*`），部署时改成真实域名 |
| 7 | 依赖 Phase 5 的前置 | 限流、CSRF 防护尚未实现（见 11 节），生产前需一并补上 |

> **不要把上面这段当成"已经写好、只差运行"**：`docker/` 目录不存在，Dockerfile 在
> `backend/` 与 `frontend/` 各自的目录下；`app/worker.py` 也不存在。
> 旧版本 README 曾贴出一份包含 `worker` 与 `chroma` 的"目标态" compose，
> 那只是设计意图，从未落地。

---

## 十一、路线图（更新）

当前状态：已完成 Phase 0-4（脚手架、用户系统、全局模型配置、文档摄取、RAG 问答），
并在 Phase 4 之后完成了一批**计划外但已实测可用**的工作。

实现路线图以 `docs/DESIGN_IMPLEMENTATION.md` 的 Phase 0-6 为准：

- [x] Phase 0：项目脚手架
- [x] Phase 1：用户系统
- [x] Phase 2：用户模型配置（全局单份配置 + Fernet 加密 + 脱敏返回）
- [x] Phase 3：文档上传与异步摄取（**进程内线程池**，非 BackgroundTasks/Celery）
- [x] Phase 4：RAG 问答（两道相关性阈值 + 防幻觉四层防护）
- [x] Phase 4.5（计划外）：个人资料与头像上传、深色主题 token 体系、侧边栏用户菜单、
      会话「重命名 / 置顶 / 删除」菜单、流式渲染修复
- [ ] Phase 5：隔离、安全、质量
- [ ] Phase 6：Docker 与简历包装

### Phase 5 的真实缺口（逐项已核对代码）

| 项 | 状态 |
| --- | --- |
| A/B 用户隔离测试 | 未做（且**没有测试框架**：后端无 pytest 配置，前端无 vitest） |
| RAG 评测集与脚本（Recall@10 ≥ 0.85、拒答准确率 ≥ 0.8） | 未做（`app/rag/evaluators.py` 不存在） |
| trace_id 与访问日志 | **已实现**（`main.py` 中间件生成 `X-Trace-Id`，含 `duration_ms` 访问日志） |
| 检索/摄取耗时日志 | **已实现**（`retrieval.py` 记录初检数 / 精排后 / 采纳数） |
| 限流 | 未做（代码中无 limiter / slowapi） |
| CORS 收紧 | **已实现白名单**（非 `*`），部署时替换为真实域名 |
| CSRF 防护 | 未做（token 存 localStorage 的必要配套） |

### Phase 6 的真实起点

| 项 | 状态 |
| --- | --- |
| `docker-compose.yml` | 仅有 backend / frontend / mysql 三个服务（见 10.2） |
| `chroma` 服务 | 未加入，导致当前 compose 跑不通 RAG 链路 |
| 独立 worker | 不存在（`app/worker.py` 未创建，摄取在 API 进程内） |
| Nginx 反代 | 未做 |
| 简历包装材料 | 未做 |

### 已知未解决的技术问题

1. **精排候选偏多**：`retrieval.py` 的 `DEFAULT_TOP_K = 30` 表示**最多 30 条候选全部进入精排**
   （`top_n=5` 只限制输出条数，不限制计算量）。早期用本地 `bge-reranker-large` 时
   CPU 上处理 10 个长候选需约 7.6 秒且超线性；改用远程 Reranker 后本地算力不再是瓶颈，
   但候选数仍直接决定远程调用延迟，建议在 Phase 5 按评测结果收敛。
2. **回答内容重复**：曾观察到 `…见 [1]切块大小默认为 700 字符，重叠为 100 字符。见 [1]`，
   疑似模型自身重复，尚未定性；提示词中已有"不要重复资料原文的大段内容"的约束但未验证。

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

> **KnowRAG** 从单用户、全局配置的 RAG 服务，升级为**多用户、Vue3 前端、全局模型配置可切换多个远程 Provider、会话严格隔离**的生产级个人知识库问答系统。

