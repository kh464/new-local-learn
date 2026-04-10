# Chinese Report And Task Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将任务详情页改为固定阶段时间线，并保证分析报告与教程输出使用中文。

**Architecture:** 前端以固定阶段序列替代原始事件平铺；后端在 deterministic 和 LLM 两条教程生成链路上统一输出中文，其中 LLM 路径增加非中文结果拒绝机制并回退到 deterministic 中文教程。

**Tech Stack:** Vue 3, Vitest, FastAPI, pytest

---

### Task 1: 阶段时间线组件

**Files:**
- Modify: `web/src/components/TaskEventTimeline.vue`
- Modify: `web/src/components/TaskEventTimeline.spec.ts`
- Modify: `web/src/pages/TaskDetailPage.vue`

- [ ] 用失败测试锁定“固定阶段 + 当前进度 + 不平铺所有百分比事件”的行为
- [ ] 让组件基于 `TaskStatus` 和固定阶段序列计算阶段状态
- [ ] 在任务详情页传入当前状态而不是仅传事件流
- [ ] 跑组件与页面测试确认行为一致

### Task 2: 前端中文文案

**Files:**
- Modify: `web/src/presentation/copy.ts`
- Modify: `web/src/components/TaskStatusCard.vue`
- Modify: `web/src/components/AnalysisResultView.vue`
- Modify: `web/src/components/AnalysisResultView.spec.ts`
- Modify: `web/src/pages/TaskDetailPage.spec.ts`

- [ ] 修复关键任务/报告页面中的乱码中文
- [ ] 统一状态、阶段、执行模式文案映射
- [ ] 更新受影响测试断言
- [ ] 跑相关 Vitest 用例

### Task 3: 中文报告与 LLM 约束

**Files:**
- Modify: `app/services/analyzers/tutor_composer.py`
- Modify: `app/services/docs/markdown_compiler.py`
- Modify: `app/services/llm/report_enhancer.py`
- Modify: `tests/unit/test_document_generation.py`
- Modify: `tests/unit/test_llm_services.py`

- [ ] 先写失败测试，覆盖 deterministic 中文输出和 LLM 中文硬约束
- [ ] 将 deterministic 教程和 Markdown 标题改为中文
- [ ] 强化 LLM system/user prompt，增加非中文结果拒绝
- [ ] 跑 pytest 确认回归通过

### Task 4: 联调验证

**Files:**
- None

- [ ] 运行相关前端测试集
- [ ] 运行相关后端测试集
- [ ] 使用真实 GitHub 仓库提交分析任务
- [ ] 确认任务成功、报告落盘且教程内容为中文
