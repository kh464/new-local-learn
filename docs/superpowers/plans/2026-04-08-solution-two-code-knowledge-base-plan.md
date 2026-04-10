# Solution Two Code Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前任务级问答升级为基于 SQLite 代码知识库的深度问答，让系统在任务成功后自动建库，并在回答时同时输出中文结论与真实代码片段。

**Architecture:** 在现有分析任务完成后追加 `build_knowledge` 阶段，自动把源码与配置文件切片写入 `artifacts/<task_id>/knowledge.db`。问答接口从知识库检索相关 chunk，再交给大模型生成中文结论，同时把文件路径、行号和代码片段直接返回给前端展示。

**Tech Stack:** FastAPI, RedisTaskStore, SQLite3/FTS5, 现有 ARQ worker, Vue 3, Vitest, Pytest

---

## 文件结构

- Modify: `D:/ai-agent/new-local-learn/app/core/models.py`
- Modify: `D:/ai-agent/new-local-learn/app/tasks/jobs.py`
- Modify: `D:/ai-agent/new-local-learn/app/api/routes/tasks.py`
- Modify: `D:/ai-agent/new-local-learn/app/storage/artifacts.py`
- Create: `D:/ai-agent/new-local-learn/app/storage/knowledge_store.py`
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/index_builder.py`
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/retriever.py`
- Create: `D:/ai-agent/new-local-learn/app/services/llm/knowledge_chat.py`
- Modify: `D:/ai-agent/new-local-learn/app/tasks/worker.py`
- Create: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_store.py`
- Create: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_index_builder.py`
- Create: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_retriever.py`
- Create: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_chat_service.py`
- Modify: `D:/ai-agent/new-local-learn/tests/tasks/test_jobs.py`
- Create: `D:/ai-agent/new-local-learn/tests/api/test_task_knowledge_chat_api.py`
- Modify: `D:/ai-agent/new-local-learn/tests/conftest.py`
- Modify: `D:/ai-agent/new-local-learn/web/src/types/contracts.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/services/api.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/services/api.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.vue`
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.vue`
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/README.md`

## Task 1: 定义知识库阶段与数据模型

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/core/models.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_bootstrap.py`

- [ ] **Step 1: 写失败测试，验证任务阶段枚举支持 `build_knowledge`，并新增知识库状态模型**
- [ ] **Step 2: 运行相关 pytest，确认因模型缺失而失败**
- [ ] **Step 3: 在模型层增加 `build_knowledge` 阶段、知识库状态字段、知识库聊天引用结构**
- [ ] **Step 4: 重新运行 pytest，确认通过**
- [ ] **Step 5: Commit**

## Task 2: 实现 SQLite 知识库存储层

**Files:**
- Create: `D:/ai-agent/new-local-learn/app/storage/knowledge_store.py`
- Modify: `D:/ai-agent/new-local-learn/app/storage/artifacts.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_store.py`

- [ ] **Step 1: 写失败测试，覆盖 SQLite 文件初始化、表创建、chunk 写入、FTS 查询**
- [ ] **Step 2: 运行 `pytest tests/unit/test_knowledge_store.py -q`，确认失败**
- [ ] **Step 3: 实现知识库文件路径、SQLite schema、文档与 chunk 存储、FTS5 索引**
- [ ] **Step 4: 重新运行 `pytest tests/unit/test_knowledge_store.py -q`，确认通过**
- [ ] **Step 5: Commit**

## Task 3: 实现源码切片与知识建库服务

**Files:**
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/index_builder.py`
- Modify: `D:/ai-agent/new-local-learn/tests/conftest.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_index_builder.py`

- [ ] **Step 1: 写失败测试，覆盖源码与配置文件切片、过滤构建产物与大文件、行号记录**
- [ ] **Step 2: 运行 `pytest tests/unit/test_knowledge_index_builder.py -q`，确认失败**
- [ ] **Step 3: 实现文件过滤规则、切片逻辑、chunk 摘要、知识库写入**
- [ ] **Step 4: 重新运行 `pytest tests/unit/test_knowledge_index_builder.py -q`，确认通过**
- [ ] **Step 5: Commit**

## Task 4: 将 `build_knowledge` 阶段接入任务流水线

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/tasks/jobs.py`
- Modify: `D:/ai-agent/new-local-learn/app/tasks/worker.py`
- Modify: `D:/ai-agent/new-local-learn/tests/tasks/test_jobs.py`

- [ ] **Step 1: 写失败测试，验证任务在报告生成后进入 `build_knowledge` 阶段，并成功产出 `knowledge.db`**
- [ ] **Step 2: 运行 `pytest tests/tasks/test_jobs.py -q`，确认失败**
- [ ] **Step 3: 在 worker 中注入知识建库依赖，并在任务流水线中追加 `build_knowledge` 阶段**
- [ ] **Step 4: 重新运行 `pytest tests/tasks/test_jobs.py -q`，确认通过**
- [ ] **Step 5: Commit**

## Task 5: 实现基于 FTS5 的代码检索器

**Files:**
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/retriever.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_retriever.py`

- [ ] **Step 1: 写失败测试，覆盖路径命中、关键词命中、文件类型加权和结果重排**
- [ ] **Step 2: 运行 `pytest tests/unit/test_knowledge_retriever.py -q`，确认失败**
- [ ] **Step 3: 实现问题预处理、FTS 召回、规则重排、上下文 chunk 选取**
- [ ] **Step 4: 重新运行 `pytest tests/unit/test_knowledge_retriever.py -q`，确认通过**
- [ ] **Step 5: Commit**

## Task 6: 实现知识库问答服务

**Files:**
- Create: `D:/ai-agent/new-local-learn/app/services/llm/knowledge_chat.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_chat_service.py`

- [ ] **Step 1: 写失败测试，覆盖“模型总结 + 返回代码片段”“模型失败降级但仍返回片段”“中文输出约束”**
- [ ] **Step 2: 运行 `pytest tests/unit/test_knowledge_chat_service.py -q`，确认失败**
- [ ] **Step 3: 实现知识库检索结果到模型提示词的组装，以及降级回答逻辑**
- [ ] **Step 4: 重新运行 `pytest tests/unit/test_knowledge_chat_service.py -q`，确认通过**
- [ ] **Step 5: Commit**

## Task 7: 升级任务聊天 API 到知识库模式

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/api/routes/tasks.py`
- Create: `D:/ai-agent/new-local-learn/tests/api/test_task_knowledge_chat_api.py`

- [ ] **Step 1: 写失败测试，覆盖“知识库未就绪不可问答”“成功问答返回代码片段”“消息持久化”**
- [ ] **Step 2: 运行 `pytest tests/api/test_task_knowledge_chat_api.py -q`，确认失败**
- [ ] **Step 3: 将聊天接口切换为依赖 SQLite 知识库和知识库问答服务**
- [ ] **Step 4: 重新运行 `pytest tests/api/test_task_knowledge_chat_api.py -q`，确认通过**
- [ ] **Step 5: Commit**

## Task 8: 扩展前端契约与 API 客户端

**Files:**
- Modify: `D:/ai-agent/new-local-learn/web/src/types/contracts.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/services/api.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/services/api.spec.ts`

- [ ] **Step 1: 写失败测试，覆盖知识库状态字段、问答返回 chunk 引用、知识库未就绪错误**
- [ ] **Step 2: 运行 `npm test -- --run src/services/api.spec.ts`，确认失败**
- [ ] **Step 3: 更新前端类型与 API 方法**
- [ ] **Step 4: 重新运行 `npm test -- --run src/services/api.spec.ts`，确认通过**
- [ ] **Step 5: Commit**

## Task 9: 升级聊天面板为知识库问答模式

**Files:**
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.vue`
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.vue`
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.spec.ts`

- [ ] **Step 1: 写失败测试，覆盖知识库构建中状态、构建失败状态、回答与代码片段并列展示**
- [ ] **Step 2: 运行 `npm test -- --run src/components/TaskChatPanel.spec.ts src/pages/TaskDetailPage.spec.ts`，确认失败**
- [ ] **Step 3: 升级聊天区展示知识库状态、代码路径、行号、代码片段原文**
- [ ] **Step 4: 重新运行 `npm test -- --run src/components/TaskChatPanel.spec.ts src/pages/TaskDetailPage.spec.ts`，确认通过**
- [ ] **Step 5: Commit**

## Task 10: 回归验证与文档

**Files:**
- Modify: `D:/ai-agent/new-local-learn/README.md`

- [ ] **Step 1: 运行后端回归测试**
- [ ] **Step 2: 运行前端目标测试**
- [ ] **Step 3: 运行前端构建**
- [ ] **Step 4: 做一轮真实联调，确认建库完成后问答深度明显优于方案一**
- [ ] **Step 5: 在 README 中补充知识库阶段、SQLite 产物和问答接口说明**
- [ ] **Step 6: Commit**
