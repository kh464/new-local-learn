# Frontend Chinese Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将前端固定界面文案和结果页显示层映射全部改为中文，同时保持后端接口和返回字段不变。

**Architecture:** 在前端新增一个集中式文案与映射模块，负责状态、阶段、执行模式、布尔值与空值占位的中文显示。页面和组件只消费这个显示层，避免在多个组件里散落内联英文文案和重复翻译逻辑。

**Tech Stack:** Vue 3、Vue Router、TypeScript、Vitest、Vue Test Utils、Vite

---

### Task 1: 建立中文显示映射层

**Files:**
- Create: `web/src/presentation/copy.ts`
- Test: `web/src/presentation/copy.spec.ts`

- [ ] **Step 1: 写失败测试，约束状态、阶段、执行模式和通用占位的中文映射**

```ts
import { describe, expect, it } from 'vitest'

import {
  formatBooleanZh,
  formatExecutionModeZh,
  formatFallbackTextZh,
  formatTaskStageZh,
  formatTaskStateZh,
} from './copy'

describe('copy', () => {
  it('formats task states in Chinese', () => {
    expect(formatTaskStateZh('queued')).toBe('排队中')
    expect(formatTaskStateZh('running')).toBe('执行中')
    expect(formatTaskStateZh('succeeded')).toBe('成功')
    expect(formatTaskStateZh('failed')).toBe('失败')
    expect(formatTaskStateZh('cancelled')).toBe('已取消')
  })

  it('formats task stages and execution modes in Chinese', () => {
    expect(formatTaskStageZh('fetch_repo')).toBe('拉取仓库')
    expect(formatTaskStageZh('scan_tree')).toBe('扫描目录')
    expect(formatExecutionModeZh('deterministic')).toBe('确定性执行')
    expect(formatExecutionModeZh('llm')).toBe('大模型生成')
    expect(formatExecutionModeZh(undefined)).toBe('计划中')
  })

  it('formats booleans and fallback text in Chinese', () => {
    expect(formatBooleanZh(true)).toBe('是')
    expect(formatBooleanZh(false)).toBe('否')
    expect(formatFallbackTextZh('')).toBe('无')
    expect(formatFallbackTextZh('unknown')).toBe('未知')
    expect(formatFallbackTextZh('not detected')).toBe('未检测到')
  })
})
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run: `npm test -- src/presentation/copy.spec.ts`

Expected: FAIL，报错找不到 `./copy` 或缺少导出函数。

- [ ] **Step 3: 写最小实现，提供统一中文映射函数**

```ts
const taskStateMap = {
  queued: '排队中',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
} as const

const taskStageMap = {
  fetch_repo: '拉取仓库',
  scan_tree: '扫描目录',
  detect_stack: '识别技术栈',
  analyze_backend: '分析后端',
  analyze_frontend: '分析前端',
  build_doc: '生成文档',
  finalize: '收尾',
} as const

const executionModeMap = {
  deterministic: '确定性执行',
  llm: '大模型生成',
  fallback: '回退',
  agent: '代理执行',
} as const

export function formatTaskStateZh(value: string): string {
  return taskStateMap[value as keyof typeof taskStateMap] ?? value
}

export function formatTaskStageZh(value?: string | null): string {
  if (!value) return '等待中'
  return taskStageMap[value as keyof typeof taskStageMap] ?? value
}

export function formatExecutionModeZh(value?: string | null): string {
  if (!value) return '计划中'
  return executionModeMap[value as keyof typeof executionModeMap] ?? value
}

export function formatBooleanZh(value: boolean): string {
  return value ? '是' : '否'
}

export function formatFallbackTextZh(value?: string | null): string {
  const normalized = (value ?? '').trim().toLowerCase()
  if (!normalized || normalized === 'none') return '无'
  if (normalized === 'unknown') return '未知'
  if (normalized === 'not detected') return '未检测到'
  return value ?? '无'
}
```

- [ ] **Step 4: 再次运行测试，确认通过**

Run: `npm test -- src/presentation/copy.spec.ts`

Expected: PASS。

- [ ] **Step 5: 提交这一小步**

```bash
git add web/src/presentation/copy.ts web/src/presentation/copy.spec.ts
git commit -m "feat: add frontend chinese copy mappings"
```

### Task 2: 中文化应用外壳、首页和提交表单

**Files:**
- Modify: `web/index.html`
- Modify: `web/src/App.vue`
- Modify: `web/src/pages/HomePage.vue`
- Modify: `web/src/components/RepositorySubmitForm.vue`
- Test: `web/src/App.spec.ts`
- Test: `web/src/pages/HomePage.spec.ts`
- Test: `web/src/components/RepositorySubmitForm.spec.ts`

- [ ] **Step 1: 先改测试，锁定首页和外壳的中文文案**

```ts
expect(wrapper.get('[data-testid="app-title"]').text()).toContain('GitHub 技术文档生成器')
expect(wrapper.get('.app-shell__eyebrow').text()).toContain('工程工作台')
expect(wrapper.text()).toContain('访问令牌')
expect(wrapper.text()).toContain('把 GitHub 项目整理成可持续阅读的技术说明')
```

```ts
expect(input.attributes('placeholder')).toBe('https://github.com/octocat/Hello-World')
expect(button.text()).toBe('开始分析')
```

- [ ] **Step 2: 运行相关测试，确认因英文旧文案而失败**

Run: `npm test -- src/App.spec.ts src/pages/HomePage.spec.ts src/components/RepositorySubmitForm.spec.ts`

Expected: FAIL，断言仍匹配到英文文案。

- [ ] **Step 3: 以最小改动实现中文外壳和首页文案**

```html
<html lang="zh-CN">
  <head>
    <title>GitHub 技术文档生成器</title>
  </head>
</html>
```

```vue
<p class="app-shell__eyebrow">工程工作台</p>
<h1 data-testid="app-title">GitHub 技术文档生成器</h1>
<RouterLink class="app-shell__link" to="/">提交任务</RouterLink>
<RouterLink class="app-shell__link" to="/admin">管理台</RouterLink>
<p class="app-shell__auth-title">访问令牌</p>
<input placeholder="粘贴 Bearer 令牌">
<button>保存令牌</button>
<button>清空</button>
```

```ts
const tokenStatus = computed(() => {
  if (tokenManagedByEnv.value) {
    return '访问令牌来自 VITE_ACCESS_TOKEN 环境变量。'
  }
  return tokenInput.value.trim() ? '访问令牌已保存在当前浏览器会话。' : '当前未保存访问令牌。'
})
```

```vue
<p class="home-hero__eyebrow">提交仓库地址并启动分析</p>
<h2 class="home-hero__title">把 GitHub 项目整理成可持续阅读的技术说明。</h2>
<p class="home-hero__subtitle">
  粘贴仓库地址后，工作台会自动生成结构化的架构概览、调用链路和实现说明。
</p>
```

```vue
<label class="repo-submit__label" for="github-url">GitHub 仓库地址</label>
<button class="repo-submit__button" type="submit" :disabled="isDisabled">
  {{ props.pending ? '提交中...' : '开始分析' }}
</button>
```

- [ ] **Step 4: 运行测试，确认外壳和首页中文化通过**

Run: `npm test -- src/App.spec.ts src/pages/HomePage.spec.ts src/components/RepositorySubmitForm.spec.ts`

Expected: PASS。

- [ ] **Step 5: 提交这一小步**

```bash
git add web/index.html web/src/App.vue web/src/pages/HomePage.vue web/src/components/RepositorySubmitForm.vue web/src/App.spec.ts web/src/pages/HomePage.spec.ts web/src/components/RepositorySubmitForm.spec.ts
git commit -m "feat: localize app shell and submit flow to chinese"
```

### Task 3: 中文化管理页、任务状态卡、时间线和任务详情页

**Files:**
- Modify: `web/src/pages/AdminPage.vue`
- Modify: `web/src/pages/TaskDetailPage.vue`
- Modify: `web/src/components/TaskStatusCard.vue`
- Modify: `web/src/components/TaskEventTimeline.vue`
- Modify: `web/src/components/TaskErrorState.vue`
- Modify: `web/src/pages/AdminPage.spec.ts`
- Modify: `web/src/pages/TaskDetailPage.spec.ts`
- Modify: `web/src/components/TaskStatusCard.spec.ts`
- Modify: `web/src/components/TaskEventTimeline.spec.ts`
- Modify: `web/src/components/TaskErrorState.spec.ts`
- Modify: `web/src/pages/AdminPage.vue` to import `web/src/presentation/copy.ts`
- Modify: `web/src/pages/TaskDetailPage.vue` to import `web/src/presentation/copy.ts`
- Modify: `web/src/components/TaskStatusCard.vue` to import `web/src/presentation/copy.ts`
- Modify: `web/src/components/TaskEventTimeline.vue` to import `web/src/presentation/copy.ts`

- [ ] **Step 1: 先改测试，锁定中文的页面标题、状态和值映射**

```ts
expect(wrapper.text()).toContain('运维控制台')
expect(wrapper.text()).toContain('最近任务')
expect(wrapper.text()).toContain('排队中')
expect(wrapper.text()).toContain('执行中')
expect(wrapper.text()).toContain('筛选任务')
```

```ts
expect(wrapper.text()).toContain('任务时间线')
expect(wrapper.text()).toContain('拉取仓库')
expect(wrapper.text()).toContain('扫描目录')
```

```ts
expect(wrapper.text()).toContain('任务失败')
expect(wrapper.text()).toContain('任务不存在')
expect(wrapper.text()).toContain('实时流：已连接')
```

- [ ] **Step 2: 运行相关测试，确认当前失败**

Run: `npm test -- src/pages/AdminPage.spec.ts src/pages/TaskDetailPage.spec.ts src/components/TaskStatusCard.spec.ts src/components/TaskEventTimeline.spec.ts src/components/TaskErrorState.spec.ts`

Expected: FAIL，页面仍显示英文。

- [ ] **Step 3: 实现最小中文化改动，并复用映射层**

```vue
<p class="status-card__label">任务 {{ status.task_id }}</p>
<h3 class="status-card__state">{{ formatTaskStateZh(status.state) }}</h3>
<p>阶段：{{ formatTaskStageZh(status.stage) }}</p>
<p>进度：{{ status.progress }}%</p>
```

```vue
<h3 class="timeline__title">任务时间线</h3>
<strong>{{ formatTaskStageZh(event.stage) || '更新' }}</strong>
```

```vue
<TaskErrorState
  v-if="isNotFound"
  title="任务不存在"
  message="请求的任务不存在，或已被系统清理。"
/>
```

```vue
<p>实时流：{{ isStreamConnected ? '已连接' : '未连接' }}</p>
<p>任务编号：{{ taskId }}</p>
{{ actionPending === 'cancel' ? '取消中...' : '取消任务' }}
{{ actionPending === 'retry' ? '重试中...' : '重新执行' }}
```

```vue
<p class="admin-hero__eyebrow">运维</p>
<h2>运维控制台</h2>
<h3>指标快照</h3>
<h3>最近任务</h3>
<h3>最近审计事件</h3>
<option value="">全部</option>
<button type="submit">应用筛选</button>
```

```ts
const taskPanelSummary = computed(() => `显示 ${taskPage.value.tasks.length} 条，共 ${taskPage.value.total} 条任务`)
```

- [ ] **Step 4: 运行测试，确认管理页和任务详情页通过**

Run: `npm test -- src/pages/AdminPage.spec.ts src/pages/TaskDetailPage.spec.ts src/components/TaskStatusCard.spec.ts src/components/TaskEventTimeline.spec.ts src/components/TaskErrorState.spec.ts`

Expected: PASS。

- [ ] **Step 5: 提交这一小步**

```bash
git add web/src/pages/AdminPage.vue web/src/pages/TaskDetailPage.vue web/src/components/TaskStatusCard.vue web/src/components/TaskEventTimeline.vue web/src/components/TaskErrorState.vue web/src/pages/AdminPage.spec.ts web/src/pages/TaskDetailPage.spec.ts web/src/components/TaskStatusCard.spec.ts web/src/components/TaskEventTimeline.spec.ts web/src/components/TaskErrorState.spec.ts
git commit -m "feat: localize admin and task detail views to chinese"
```

### Task 4: 中文化结果页卡片、下载区和动态值显示

**Files:**
- Modify: `web/src/components/AnalysisResultView.vue`
- Modify: `web/src/components/AnalysisResultView.spec.ts`
- Modify: `web/src/components/ResultSectionCard.vue` only if existing props need Chinese defaults
- Modify: `web/src/components/AnalysisResultView.vue` to import `web/src/presentation/copy.ts`

- [ ] **Step 1: 先改测试，锁定结果页中文标题和动态映射**

```ts
expect(wrapper.text()).toContain('项目概览')
expect(wrapper.text()).toContain('识别到的技术栈')
expect(wrapper.text()).toContain('后端分析')
expect(wrapper.text()).toContain('前端分析')
expect(wrapper.text()).toContain('部署分析')
expect(wrapper.text()).toContain('新手学习指南')
expect(wrapper.text()).toContain('覆盖说明')
expect(wrapper.text()).toContain('代理执行情况')
expect(wrapper.text()).toContain('下载 Markdown')
expect(wrapper.text()).toContain('下载 HTML')
expect(wrapper.text()).toContain('下载 PDF')
expect(wrapper.text()).toContain('已启用：是')
expect(wrapper.text()).toContain('兜底角色：critic')
```

```ts
expect(wrapper.text()).toContain('框架：vue')
expect(wrapper.text()).toContain('状态管理：pinia')
expect(wrapper.text()).toContain('环境变量文件：.env.example')
expect(wrapper.text()).toContain('依赖 redis')
```

- [ ] **Step 2: 运行结果页测试，确认因英文文案失败**

Run: `npm test -- src/components/AnalysisResultView.spec.ts`

Expected: FAIL。

- [ ] **Step 3: 实现结果页中文标签和动态值显示**

```vue
<ResultSectionCard title="项目概览" eyebrow="仓库">
  <p>{{ result.repo_summary.file_count }} 个文件已扫描</p>
</ResultSectionCard>

<ResultSectionCard title="识别到的技术栈" eyebrow="技术栈">
```

```vue
<p>框架：{{ formatFallbackTextZh(result.frontend_summary.framework) }}</p>
<p>构建工具：{{ formatFallbackTextZh(result.frontend_summary.bundler) }}</p>
<p>状态管理：{{ formatFallbackTextZh(result.frontend_summary.state_manager) }}</p>
```

```vue
<p>环境变量文件：{{ result.deploy_summary.environment_files.join(', ') || '无' }}</p>
<p>Kubernetes 清单：{{ result.deploy_summary.manifests.join(', ') || '无' }}</p>
{{ service.name }}<span v-if="service.depends_on?.length"> 依赖 {{ service.depends_on.join(', ') }}</span>
```

```vue
<h4>请求生命周期</h4>
<h4>运行步骤</h4>
<h4>常见陷阱</h4>
<h4>代码走读</h4>
<h4>常见问题</h4>
<h4>下一步</h4>
<h4>自检问题</h4>
```

```vue
<ResultSectionCard v-if="result.agent_metadata" title="代理执行情况" eyebrow="编排器">
  <p>已启用：{{ formatBooleanZh(result.agent_metadata.enabled) }}</p>
  <p>使用角色：{{ usedRolesText }}</p>
  <p>兜底角色：{{ fallbackRolesText }}</p>
  <li v-for="node in executionNodes" :key="node.node">
    {{ node.node }}：{{ formatFallbackTextZh(node.status) }}（{{ formatExecutionModeZh(node.execution_mode) }}）
  </li>
</ResultSectionCard>
```

- [ ] **Step 4: 运行测试，确认结果页中文化通过**

Run: `npm test -- src/components/AnalysisResultView.spec.ts`

Expected: PASS。

- [ ] **Step 5: 提交这一小步**

```bash
git add web/src/components/AnalysisResultView.vue web/src/components/AnalysisResultView.spec.ts
git commit -m "feat: localize analysis result view to chinese"
```

### Task 5: 全量验证前端中文化变更

**Files:**
- Verify only: `web/src/App.spec.ts`
- Verify only: `web/src/pages/HomePage.spec.ts`
- Verify only: `web/src/pages/AdminPage.spec.ts`
- Verify only: `web/src/pages/TaskDetailPage.spec.ts`
- Verify only: `web/src/components/RepositorySubmitForm.spec.ts`
- Verify only: `web/src/components/TaskStatusCard.spec.ts`
- Verify only: `web/src/components/TaskEventTimeline.spec.ts`
- Verify only: `web/src/components/TaskErrorState.spec.ts`
- Verify only: `web/src/components/AnalysisResultView.spec.ts`

- [ ] **Step 1: 跑前端相关测试集合**

Run: `npm test -- src/App.spec.ts src/pages/HomePage.spec.ts src/pages/AdminPage.spec.ts src/pages/TaskDetailPage.spec.ts src/components/RepositorySubmitForm.spec.ts src/components/TaskStatusCard.spec.ts src/components/TaskEventTimeline.spec.ts src/components/TaskErrorState.spec.ts src/components/AnalysisResultView.spec.ts`

Expected: PASS。

- [ ] **Step 2: 跑前端构建验证**

Run: `npm run build`

Expected: exit 0，Vite 构建成功。

- [ ] **Step 3: 提交最终整合改动**

```bash
git add web/src web/index.html
git commit -m "feat: localize frontend interface to chinese"
```
