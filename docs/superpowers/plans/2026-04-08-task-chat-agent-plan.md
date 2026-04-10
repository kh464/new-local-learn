# Task Chat Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在任务分析成功后，为任务详情页增加固定聊天区，支持用户基于当前仓库继续提问，并返回带代码依据的中文回答。

**Architecture:** 复用现有任务体系，在后端新增任务级聊天接口和轻量检索服务，在前端任务详情页新增聊天面板。回答流程为“读取任务结果 -> 检索相关文件片段 -> 调用大模型生成结构化中文回答 -> 渲染引用与回答”，并保留基于已有任务 token 的访问控制。

**Tech Stack:** FastAPI, RedisTaskStore, ARQ 任务产物, 现有 LLM 客户端, Vue 3, Vitest, Pytest

---

## 文件结构

- 修改: `D:/ai-agent/new-local-learn/app/core/models.py`
- 修改: `D:/ai-agent/new-local-learn/app/api/routes/tasks.py`
- 新建: `D:/ai-agent/new-local-learn/app/services/llm/repo_chat.py`
- 修改: `D:/ai-agent/new-local-learn/app/tasks/worker.py`
- 修改: `D:/ai-agent/new-local-learn/app/storage/task_store.py`
- 新建: `D:/ai-agent/new-local-learn/tests/api/test_task_chat_api.py`
- 新建: `D:/ai-agent/new-local-learn/tests/unit/test_repo_chat_service.py`
- 修改: `D:/ai-agent/new-local-learn/web/src/types/contracts.ts`
- 修改: `D:/ai-agent/new-local-learn/web/src/services/api.ts`
- 新建: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.vue`
- 新建: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.spec.ts`
- 修改: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.vue`
- 修改: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.spec.ts`

## Task 1: 定义后端聊天模型与存储接口

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/core/models.py`
- Modify: `D:/ai-agent/new-local-learn/app/storage/task_store.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_task_store.py`

- [ ] Step 1: 先为聊天消息和聊天响应写失败测试
- [ ] Step 2: 运行相关 pytest，确认缺少模型或存储能力导致失败
- [ ] Step 3: 在模型层新增任务聊天请求、聊天消息、聊天引用、聊天响应类型
- [ ] Step 4: 在 RedisTaskStore 中新增聊天消息读写方法
- [ ] Step 5: 重新运行 pytest，确认通过

## Task 2: 实现仓库问答服务

**Files:**
- Create: `D:/ai-agent/new-local-learn/app/services/llm/repo_chat.py`
- Modify: `D:/ai-agent/new-local-learn/app/tasks/worker.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_repo_chat_service.py`

- [ ] Step 1: 为“成功生成中文回答、必须带引用、LLM 失败时走降级回答”写失败测试
- [ ] Step 2: 运行单测，确认失败原因正确
- [ ] Step 3: 实现轻量检索与提示词编排服务
- [ ] Step 4: 在 worker 启动依赖中注入仓库问答生成器
- [ ] Step 5: 重新运行单测，确认通过

## Task 3: 暴露任务级聊天 API

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/api/routes/tasks.py`
- Test: `D:/ai-agent/new-local-learn/tests/api/test_task_chat_api.py`

- [ ] Step 1: 为“成功任务可问答、非成功任务被拒绝、消息可回读”写失败测试
- [ ] Step 2: 运行 API 测试，确认失败原因正确
- [ ] Step 3: 新增 `POST /api/v1/tasks/{task_id}/chat` 与 `GET /api/v1/tasks/{task_id}/chat/messages`
- [ ] Step 4: 接入任务访问控制、任务状态校验、消息持久化和问答服务
- [ ] Step 5: 重新运行 API 测试，确认通过

## Task 4: 扩展前端契约与 API 客户端

**Files:**
- Modify: `D:/ai-agent/new-local-learn/web/src/types/contracts.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/services/api.ts`
- Test: `D:/ai-agent/new-local-learn/web/src/services/api.spec.ts`

- [ ] Step 1: 为聊天消息查询和提交 API 写失败测试
- [ ] Step 2: 运行 vitest 指定用例，确认失败
- [ ] Step 3: 增加前端聊天类型与 `fetchTaskChatMessages`、`submitTaskQuestion`
- [ ] Step 4: 重新运行相关 vitest，确认通过

## Task 5: 实现任务详情页聊天区

**Files:**
- Create: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.vue`
- Test: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.spec.ts`

- [ ] Step 1: 为“加载历史消息、发送问题、展示引用和错误状态”写失败测试
- [ ] Step 2: 运行组件测试，确认失败
- [ ] Step 3: 实现固定聊天区组件
- [ ] Step 4: 重新运行组件测试，确认通过

## Task 6: 接入任务详情页

**Files:**
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.vue`
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.spec.ts`

- [ ] Step 1: 为“仅成功任务显示聊天区”写失败测试
- [ ] Step 2: 运行页面测试，确认失败
- [ ] Step 3: 将聊天区接入任务详情页布局
- [ ] Step 4: 重新运行页面测试，确认通过

## Task 7: 端到端验证

**Files:**
- Modify: `D:/ai-agent/new-local-learn/README.md`

- [ ] Step 1: 运行后端 pytest 目标用例
- [ ] Step 2: 运行前端 vitest 目标用例
- [ ] Step 3: 运行前端构建
- [ ] Step 4: 做一轮真实联调，验证成功任务可继续提问
- [ ] Step 5: 在 README 中补充任务级问答接口和页面能力说明
