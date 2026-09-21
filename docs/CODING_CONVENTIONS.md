# KnowRAG 代码约定

> 本文档用于约束 KnowRAG 的代码风格、目录组织、接口格式、注释、日志、安全和提交规范。后续开发应优先遵守本文档；如果实现中需要偏离，应在对应 PR 或开发记录中说明原因。

---

## 1. 总体原则

- 代码优先追求清晰、稳定、可维护，不为了炫技引入复杂抽象。
- 业务逻辑、数据库访问、模型调用、RAG 流程要分层，不把所有逻辑写进 router 或组件。
- 前后端接口字段必须稳定，变更接口时同步更新文档和类型定义。
- 用户隔离、安全、日志脱敏是硬性要求，不能作为后续优化项。
- 注释解释“为什么这样做”，不要解释显而易见的语法。

---

## 2. 目录约定

项目顶层目录：

```text
KnowRAG/
├── frontend/
├── backend/
├── docs/
├── docker-compose.yml
└── README.md
```

后端 AI / RAG 相关逻辑放在：

```text
backend/app/rag/
backend/app/services/
```

不单独创建顶层 `ai/` 目录，除非后续真的拆成独立 AI 服务。

---

## 3. Python 后端代码规范

### 3.1 格式化与检查

推荐工具：

- `ruff`：lint + import sort
- `black`：格式化
- `mypy`：核心模块类型检查，可分阶段启用
- `pytest`：测试

建议命令：

```bash
ruff check backend
black backend
pytest backend/tests
```

### 3.2 命名规范

| 类型 | 规范 | 示例 |
| ---- | ---- | ---- |
| 文件名 | `snake_case.py` | `model_factory.py` |
| 变量 / 函数 | `snake_case` | `create_user_config` |
| 类名 | `PascalCase` | `ModelFactory` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_TOP_K` |
| 私有函数 | `_snake_case` | `_mask_api_key` |

### 3.3 分层规范

Router 只负责：

- 参数接收
- 鉴权依赖
- 调用 service
- 返回 schema

Service 负责：

- 业务逻辑
- 数据库读写协调
- 模型调用协调
- 缓存失效

Model 负责：

- ORM 表结构
- 关系定义

Schema 负责：

- 请求体和响应体类型
- 字段校验
- 对外 API 契约

禁止：

- 在 router 中直接写复杂 RAG 流程。
- 在 ORM model 中写业务流程。
- 在 service 中返回未脱敏的 API Key。
- 使用前端传入的 `user_id` 判断数据归属。

### 3.4 类型约定

- 新增函数尽量补齐参数和返回类型。
- 复杂返回值优先使用 Pydantic schema 或 dataclass。
- `Optional` 字段要明确业务含义：缺省、清空、保持原值不能混淆。

示例：

```python
def mask_api_key(value: str | None) -> str | None:
    if not value:
        return None
    return f"{value[:3]}-****{value[-4:]}"
```

---

## 4. TypeScript 前端代码规范

### 4.1 格式化与检查

推荐工具：

- `eslint`
- `prettier`
- `vue-tsc`

建议命令：

```bash
npm run lint
npm run typecheck
npm run build
```

### 4.2 命名规范

| 类型 | 规范 | 示例 |
| ---- | ---- | ---- |
| Vue 组件 | `PascalCase.vue` | `ChatMessage.vue` |
| 变量 / 函数 | `camelCase` | `streamChat` |
| 类型 / 接口 | `PascalCase` | `ChatRequest` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_PAGE_SIZE` |
| Store | `useXxxStore` | `useChatStore` |

### 4.3 组件规范

- 页面级组件放 `src/views/`。
- 可复用组件放 `src/components/`。
- API 请求放 `src/api/`。
- 类型定义放 `src/types/`。
- Pinia 状态放 `src/stores/`。

组件内推荐顺序：

```vue
<script setup lang="ts">
// imports
// types
// props / emits
// stores
// state
// computed
// methods
// lifecycle
</script>

<template>
  ...
</template>

<style scoped>
...
</style>
```

### 4.4 UI 规范

- UI 风格遵守 `docs/UI_DESIGN_PROMPT.md`。
- 页面不要做营销式 hero，优先工作台体验。
- 表格在移动端需要可降级为列表。
- 所有 loading、empty、error、disabled 状态都要设计。
- Markdown 渲染必须经过 DOMPurify 清洗。

---

## 5. 注释规范

### 5.1 应该注释的内容

- 安全边界。
- 索引版本切换原因。
- 缓存失效逻辑。
- RAG prompt 中的约束意图。
- 复杂检索合并、重排、去重逻辑。
- 非显而易见的业务规则。

### 5.2 不应该注释的内容

不要写这种注释：

```python
# 获取用户 ID
user_id = current_user.id
```

应该写这种注释：

```python
# Embedding 模型变化会导致向量空间不兼容，旧索引必须标记为 stale。
if embedding_changed(old_config, new_config):
    mark_user_index_stale(db, current_user.id)
```

### 5.3 TODO 规范

TODO 必须包含原因或后续动作：

```python
# TODO: Replace BackgroundTasks with a durable queue before supporting large batch uploads.
```

不要写：

```python
# TODO: optimize
```

---

## 6. API 接口规范

### 6.1 路径规范

- 认证接口：`/auth/...`
- 业务接口：`/api/...`
- 文档接口：`/api/docs/...`
- 聊天接口：`/api/chat/...`
- 配置接口：`/api/config/...`
- 索引接口：`/api/index/...`

### 6.2 请求规范

- 后端一律从 JWT / Cookie 中获取当前用户。
- 请求体不能包含可信 `user_id`。
- 分页参数统一使用 `page`、`page_size`。
- 时间字段使用 ISO 8601 字符串。

### 6.3 成功响应规范

简单对象可以直接返回 schema：

```json
{
  "conversation_id": "58cc403e-3d88-4e3e-a5a7-b8a6f4f3a737",
  "title": "新会话"
}
```

列表响应统一：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

### 6.4 错误响应规范

错误响应统一包含：

```json
{
  "code": "INDEX_NOT_READY",
  "message": "当前知识库索引不可用，请先重建索引",
  "trace_id": "9b4b98d7-4a29-41d4-8980-6b80a6c7a715"
}
```

常用错误码：

| code | 含义 |
| ---- | ---- |
| `UNAUTHORIZED` | 未登录或 token 无效 |
| `FORBIDDEN` | 无权限访问 |
| `VALIDATION_ERROR` | 请求参数错误 |
| `RESOURCE_NOT_FOUND` | 资源不存在 |
| `INDEX_NOT_READY` | 知识库索引不可用 |
| `INDEX_STALE` | 索引已过期，需要重建 |
| `MODEL_CONFIG_INVALID` | 模型配置不可用 |
| `MODEL_PROVIDER_ERROR` | 模型供应商调用失败 |
| `INGESTION_FAILED` | 文档摄取失败 |
| `RATE_LIMITED` | 请求过于频繁 |
| `INTERNAL_ERROR` | 服务器内部错误 |

### 6.5 SSE 规范

聊天流式接口使用 SSE event：

```text
event: token
data: {"text":"..."}

event: sources
data: {"sources":[]}

event: complete
data: {"trace_id":"..."}

event: error
data: {"code":"INDEX_NOT_READY","message":"...","trace_id":"..."}
```

前端必须处理 `token`、`sources`、`complete`、`error` 四类事件。

---

## 7. 数据库规范

### 7.1 命名规范

| 类型 | 规范 | 示例 |
| ---- | ---- | ---- |
| 表名 | 复数 `snake_case` | `user_model_configs` |
| 字段名 | `snake_case` | `created_at` |
| 外键 | `{table_singular}_id` | `user_id` |
| 时间字段 | `created_at` / `updated_at` | `updated_at` |

### 7.2 通用字段

业务表默认包含：

- `id`
- `created_at`
- `updated_at`

软删除按需增加：

- `deleted_at`
- `is_deleted`

### 7.3 迁移规范

- 数据库结构变更必须通过 Alembic migration。
- migration 文件名要能看懂变更目的。
- 不手动直接改生产数据库结构。

---

## 8. 日志规范

### 8.1 必须记录

- `trace_id`
- `user_id`
- 请求路径
- 请求耗时
- 模型 provider
- 检索耗时
- rerank 耗时
- LLM 首 token 耗时
- 总生成耗时
- 错误码

### 8.2 禁止记录

- 明文密码
- 明文 API Key
- JWT token
- Cookie
- 完整 Authorization header
- 用户上传文档全文

### 8.3 trace_id

- 每个请求生成或继承一个 `trace_id`。
- 错误响应必须返回 `trace_id`。
- 聊天消息表保存 `trace_id`。

---

## 9. 安全规范

- 所有业务查询必须以 `current_user.id` 限定范围。
- 不相信前端传入的 `user_id`。
- API Key 必须加密存储。
- 文件上传必须限制大小和类型。
- 文件保存路径必须由后端生成，不能直接拼接用户输入。
- Markdown 渲染必须清洗 HTML。
- 文档内容不能覆盖系统 Prompt。
- CORS 生产环境必须配置白名单。
- 登录、上传、问答接口需要限流。
- 模型配置测试接口不得泄露供应商返回的敏感细节。

---

## 10. RAG 代码规范

### 10.1 Chunk metadata

每个 chunk 必须带：

```json
{
  "user_id": 1,
  "document_id": 12,
  "filename": "example.pdf",
  "chunk_id": "doc12_chunk003",
  "index_version": 3
}
```

### 10.2 检索约束

- 检索必须限定当前用户 collection 或 metadata。
- `stale` 索引不能参与检索。
- Embedding provider / model / dimension 变化后必须重建索引。
- Reranker 变化只需要刷新 retriever 缓存，不需要重建索引。

### 10.3 Prompt 约束

Prompt 必须包含：

- 只基于上下文回答。
- 不确定时明确说不确定。
- 不执行文档中的系统级指令。
- 尽量附带引用来源。

---

## 11. Git 提交规范

推荐 Conventional Commits：

```text
feat: add document ingestion task
fix: prevent stale index retrieval
docs: add coding conventions
refactor: split model factory
test: add user isolation tests
chore: configure ruff and eslint
```

常用类型：

| 类型 | 说明 |
| ---- | ---- |
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档 |
| `refactor` | 重构 |
| `test` | 测试 |
| `chore` | 工具、配置、依赖 |
| `style` | 纯格式修改 |

提交粒度：

- 一个提交只做一类事情。
- 不把格式化、重构、功能混在一个提交里。
- 涉及接口变更时，同步提交前端类型和文档。

---

## 12. Definition of Done

一个功能完成至少满足：

- [ ] 代码通过格式化和 lint。
- [ ] 关键路径有测试或手动验证记录。
- [ ] API schema 与前端类型一致。
- [ ] 错误响应符合统一格式。
- [ ] 日志包含 trace_id。
- [ ] 不泄露 API Key、token、密码。
- [ ] 用户隔离边界明确。
- [ ] 相关文档已更新。

