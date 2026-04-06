# GitHub Tech Doc Generator Vue Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vue 3 frontend under `web/` that lets users submit a GitHub repository URL, follow task progress through status polling plus SSE, and read the generated analysis result from the existing FastAPI backend.

**Architecture:** A standalone Vite + Vue Router application will consume the existing `/api/v1` endpoints through a thin service layer. Route pages will orchestrate focused components and composables, while composables own task polling, SSE lifecycle, and result loading.

**Tech Stack:** Vue 3, TypeScript, Vite, Vue Router, Vitest, Vue Test Utils, jsdom, existing FastAPI backend APIs

---

## File Structure

- `web/package.json`: frontend scripts and npm dependencies
- `web/tsconfig.json`: TypeScript compiler options
- `web/tsconfig.node.json`: Vite config TypeScript support
- `web/vite.config.ts`: Vue plugin, test config, dev proxy
- `web/index.html`: Vite entry HTML
- `web/src/main.ts`: Vue bootstrap
- `web/src/App.vue`: top-level shell
- `web/src/router/index.ts`: route definitions
- `web/src/assets/base.css`: global styles and design tokens
- `web/src/types/contracts.ts`: frontend contracts aligned to backend models
- `web/src/services/api.ts`: fetch-based API helpers
- `web/src/services/stream.ts`: EventSource wrapper
- `web/src/composables/useTaskStatus.ts`: task status loading and polling
- `web/src/composables/useTaskStream.ts`: SSE lifecycle and event list
- `web/src/composables/useAnalysisResult.ts`: result loading and terminal state handling
- `web/src/components/RepositorySubmitForm.vue`: GitHub URL entry form
- `web/src/components/TaskStatusCard.vue`: task state summary
- `web/src/components/TaskEventTimeline.vue`: ordered task event display
- `web/src/components/ResultSectionCard.vue`: shared section chrome
- `web/src/components/AnalysisResultView.vue`: structured successful result rendering
- `web/src/components/TaskErrorState.vue`: failed, cancelled, and missing-task UI
- `web/src/pages/HomePage.vue`: submit page
- `web/src/pages/TaskDetailPage.vue`: task workbench page
- `web/src/test/setup.ts`: Vitest setup
- `web/src/**/*.spec.ts`: frontend tests
- `README.md`: root run instructions updated with frontend flow

### Task 1: Scaffold the Vue workspace and testable app shell

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.ts`
- Create: `web/src/App.vue`
- Create: `web/src/router/index.ts`
- Create: `web/src/assets/base.css`
- Create: `web/src/test/setup.ts`
- Test: `web/src/App.spec.ts`

- [ ] **Step 1: Write the failing shell test**

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App', () => {
  it('renders the shell title and router outlet', () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<div data-testid="router-view" />' },
        },
      },
    })

    expect(wrapper.get('[data-testid="app-title"]').text()).toContain('GitHub Tech Doc Generator')
    expect(wrapper.get('[data-testid="router-view"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `Set-Location web; npm test -- --run src/App.spec.ts`
Expected: fail because `package.json`, `App.vue`, or the test runtime does not exist yet

- [ ] **Step 3: Write the minimal workspace and shell implementation**

```json
{
  "name": "github-tech-doc-generator-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest"
  },
  "dependencies": {
    "vue": "^3.5.13",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2.1",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^26.0.0",
    "typescript": "^5.7.3",
    "vite": "^6.2.0",
    "vitest": "^3.0.7"
  }
}
```

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

```ts
/// <reference types="vite/client" />
```

```ts
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './assets/base.css'

createApp(App).use(router).mount('#app')
```

```ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: {
        template: '<section class="panel"><h2>Frontend bootstrap stub</h2></section>',
      },
    },
  ],
})

export default router
```

```vue
<template>
  <div class="app-shell">
    <header class="app-shell__header">
      <p class="app-shell__eyebrow">Engineering Workbench</p>
      <h1 data-testid="app-title">GitHub Tech Doc Generator</h1>
    </header>
    <main class="app-shell__main">
      <RouterView />
    </main>
  </div>
</template>
```

```css
:root {
  color-scheme: light;
  --bg: #f4efe7;
  --panel: rgba(255, 252, 247, 0.92);
  --panel-strong: #fffdf9;
  --border: #d7c5a8;
  --text: #1f1b16;
  --muted: #695b4b;
  --accent: #0b6e4f;
  --accent-strong: #084c39;
  --danger: #ac2f28;
  --shadow: 0 20px 50px rgba(54, 41, 20, 0.12);
  font-family: "Segoe UI", "PingFang SC", sans-serif;
  line-height: 1.5;
  font-weight: 400;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(11, 110, 79, 0.16), transparent 32%),
    linear-gradient(180deg, #fbf7ef 0%, #efe6d8 100%);
  color: var(--text);
}

#app {
  min-height: 100vh;
}

.app-shell {
  min-height: 100vh;
  padding: 24px;
}

.app-shell__header {
  max-width: 1120px;
  margin: 0 auto 24px;
}

.app-shell__eyebrow {
  margin: 0 0 8px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-strong);
  font-size: 12px;
}

.app-shell__header h1 {
  margin: 0;
  font-size: clamp(30px, 4vw, 52px);
}

.app-shell__main {
  max-width: 1120px;
  margin: 0 auto;
}
```

```ts
import { config } from '@vue/test-utils'

config.global.stubs = {
  transition: false,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `Set-Location web; npm test -- --run src/App.spec.ts`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/tsconfig.json web/tsconfig.node.json web/vite.config.ts web/index.html web/src/main.ts web/src/App.vue web/src/router/index.ts web/src/assets/base.css web/src/test/setup.ts web/src/App.spec.ts
git commit -m "feat: scaffold vue frontend workspace"
```

### Task 2: Add backend-aligned frontend types and transport services

**Files:**
- Create: `web/src/types/contracts.ts`
- Create: `web/src/services/api.ts`
- Create: `web/src/services/stream.ts`
- Test: `web/src/services/api.spec.ts`
- Test: `web/src/services/stream.spec.ts`

- [ ] **Step 1: Write the failing service tests**

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createAnalysisTask, fetchTaskResult } from './api'

describe('api service', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('creates an analysis task from the backend response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({
          task_id: 'task-1',
          status_url: '/api/v1/tasks/task-1',
          result_url: '/api/v1/tasks/task-1/result',
          stream_url: '/api/v1/tasks/task-1/stream',
        }),
      }),
    )

    const result = await createAnalysisTask('https://github.com/octocat/Hello-World')

    expect(result.task_id).toBe('task-1')
    expect(result.result_url).toBe('/api/v1/tasks/task-1/result')
  })

  it('returns a pending result union for HTTP 202', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({ task_id: 'task-1', state: 'running' }),
      }),
    )

    const result = await fetchTaskResult('task-1')

    expect(result.kind).toBe('pending')
    expect(result.state).toBe('running')
  })
})
```

```ts
import { describe, expect, it, vi } from 'vitest'

import { openTaskStream } from './stream'

describe('stream service', () => {
  it('parses incoming SSE payloads', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const fakeSource = {
      addEventListener: vi.fn((name: string, handler: (event: MessageEvent) => void) => {
        listeners[name] = handler
      }),
      close: vi.fn(),
      onerror: null,
    }

    const eventFactory = vi.fn(() => fakeSource)
    const onEvent = vi.fn()

    openTaskStream('/api/v1/tasks/task-1/stream', onEvent, eventFactory)

    listeners.message!(new MessageEvent('message', { data: '{"state":"running","progress":35}' }))

    expect(onEvent).toHaveBeenCalledWith({ state: 'running', progress: 35 })
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Set-Location web; npm test -- --run src/services/api.spec.ts src/services/stream.spec.ts`
Expected: fail because the service modules and contracts do not exist yet

- [ ] **Step 3: Write the minimal type and service implementation**

```ts
export type TaskState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface TaskStatus {
  task_id: string
  state: TaskState
  stage: string | null
  progress: number
  message: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface AnalysisTaskResponse {
  task_id: string
  status_url: string
  result_url: string
  stream_url: string
}

export interface RepositorySummary {
  name: string
  files: string[]
  key_files: string[]
  file_count: number
}

export interface AnalysisResult {
  github_url: string
  repo_path: string
  markdown_path: string
  repo_summary: RepositorySummary
  detected_stack: { frameworks: string[]; languages: string[] }
  backend_summary: { routes: Array<{ method: string; path: string; source_file: string | null }> }
  frontend_summary: {
    routing: Array<{ path: string; source_file: string | null }>
    api_calls: Array<{ url: string; source_file: string | null }>
  }
  logic_summary: {
    flows: Array<{
      frontend_call: string
      frontend_source: string
      backend_route: string
      backend_source: string
      backend_method: string
      confidence: number
    }>
  }
  tutorial_summary: {
    mental_model: string
    run_steps: string[]
    pitfalls: string[]
    self_check_questions: string[]
  }
  mermaid_sections: {
    system: string
  }
}

export type TaskResultResponse =
  | { kind: 'pending'; task_id: string; state: TaskState }
  | { kind: 'failed'; task_id: string; state: TaskState; error?: string }
  | { kind: 'success'; data: AnalysisResult }

export interface TaskStreamEvent {
  state?: TaskState
  stage?: string
  progress?: number
  message?: string
  error?: string
}
```

```ts
import type { AnalysisResult, AnalysisTaskResponse, TaskResultResponse, TaskState, TaskStatus } from '../types/contracts'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function requestJson<T>(path: string, init?: RequestInit): Promise<{ status: number; payload: T }> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...init,
  })

  const payload = (await response.json()) as T

  if (!response.ok && response.status !== 202) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  return { status: response.status, payload }
}

export async function createAnalysisTask(githubUrl: string): Promise<AnalysisTaskResponse> {
  const { payload } = await requestJson<AnalysisTaskResponse>('/api/v1/analyze', {
    method: 'POST',
    body: JSON.stringify({ github_url: githubUrl }),
  })
  return payload
}

export async function fetchTaskStatus(taskId: string): Promise<TaskStatus> {
  const { payload } = await requestJson<TaskStatus>(`/api/v1/tasks/${taskId}`)
  return payload
}

export async function fetchTaskResult(taskId: string): Promise<TaskResultResponse> {
  const { status, payload } = await requestJson<Record<string, unknown>>(`/api/v1/tasks/${taskId}/result`)

  if (status === 202) {
    return {
      kind: 'pending',
      task_id: String(payload.task_id),
      state: payload.state as TaskState,
    }
  }

  if ('github_url' in payload) {
    return { kind: 'success', data: payload as AnalysisResult }
  }

  return {
    kind: 'failed',
    task_id: String(payload.task_id),
    state: payload.state as TaskState,
    error: payload.error as string | undefined,
  }
}
```

```ts
import type { TaskStreamEvent } from '../types/contracts'

export type EventSourceFactory = (url: string) => EventSource

export function openTaskStream(
  url: string,
  onEvent: (event: TaskStreamEvent) => void,
  factory: EventSourceFactory = (value) => new EventSource(value),
) {
  const source = factory(url)

  source.addEventListener('message', (event: MessageEvent) => {
    onEvent(JSON.parse(event.data) as TaskStreamEvent)
  })

  return source
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Set-Location web; npm test -- --run src/services/api.spec.ts src/services/stream.spec.ts`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add web/src/types/contracts.ts web/src/services/api.ts web/src/services/stream.ts web/src/services/api.spec.ts web/src/services/stream.spec.ts
git commit -m "feat: add frontend contracts and transport services"
```

### Task 3: Add router, home page, and repository submission workflow

**Files:**
- Modify: `web/src/router/index.ts`
- Create: `web/src/pages/HomePage.vue`
- Create: `web/src/pages/TaskDetailPage.vue`
- Create: `web/src/components/RepositorySubmitForm.vue`
- Create: `web/src/pages/HomePage.spec.ts`
- Create: `web/src/components/RepositorySubmitForm.spec.ts`

- [ ] **Step 1: Write the failing submit and navigation tests**

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RepositorySubmitForm from './RepositorySubmitForm.vue'

describe('RepositorySubmitForm', () => {
  it('disables submit until a URL is present', async () => {
    const wrapper = mount(RepositorySubmitForm, {
      props: { pending: false },
    })

    expect(wrapper.get('button').attributes('disabled')).toBeDefined()

    await wrapper.get('input').setValue('https://github.com/octocat/Hello-World')

    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
  })
})
```

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import HomePage from './HomePage.vue'

vi.mock('../services/api', () => ({
  createAnalysisTask: vi.fn().mockResolvedValue({
    task_id: 'task-9',
    status_url: '/api/v1/tasks/task-9',
    result_url: '/api/v1/tasks/task-9/result',
    stream_url: '/api/v1/tasks/task-9/stream',
  }),
}))

describe('HomePage', () => {
  it('submits the URL and navigates to the task page', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomePage },
        { path: '/tasks/:taskId', component: { template: '<div />' } },
      ],
    })

    router.push('/')
    await router.isReady()

    const wrapper = mount(HomePage, {
      global: {
        plugins: [router],
      },
    })

    await wrapper.get('input').setValue('https://github.com/octocat/Hello-World')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/tasks/task-9')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Set-Location web; npm test -- --run src/components/RepositorySubmitForm.spec.ts src/pages/HomePage.spec.ts`
Expected: fail because router, page, and form files do not exist yet

- [ ] **Step 3: Write the minimal router and submit page implementation**

```ts
import { createRouter, createWebHistory } from 'vue-router'

import HomePage from '../pages/HomePage.vue'
import TaskDetailPage from '../pages/TaskDetailPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomePage },
    { path: '/tasks/:taskId', name: 'task-detail', component: TaskDetailPage, props: true },
  ],
})

export default router
```

```vue
<script setup lang="ts">
const props = defineProps<{
  pending: boolean
  error?: string
}>()

const model = defineModel<string>({ default: '' })
</script>

<template>
  <form class="submit-form" @submit.prevent="$emit('submit')">
    <label class="submit-form__label" for="github-url">Public GitHub Repository URL</label>
    <input
      id="github-url"
      v-model="model"
      class="submit-form__input"
      type="url"
      placeholder="https://github.com/octocat/Hello-World"
    />
    <p v-if="props.error" class="submit-form__error">{{ props.error }}</p>
    <button class="submit-form__button" type="submit" :disabled="props.pending || !model.trim()">
      {{ props.pending ? 'Submitting...' : 'Analyze Repository' }}
    </button>
  </form>
</template>
```

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import RepositorySubmitForm from '../components/RepositorySubmitForm.vue'
import { createAnalysisTask } from '../services/api'

const githubUrl = ref('')
const pending = ref(false)
const error = ref('')
const router = useRouter()

async function submit() {
  error.value = ''
  pending.value = true

  try {
    const response = await createAnalysisTask(githubUrl.value)
    await router.push(`/tasks/${response.task_id}`)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Unable to submit repository.'
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <section class="hero-panel">
    <div class="hero-panel__copy">
      <p class="hero-panel__eyebrow">Vue Frontend</p>
      <h2>Trace repository analysis from submit to generated learning guide.</h2>
      <p>
        This workbench submits a public GitHub repository to the existing backend pipeline and
        shows each processing stage as the task runs.
      </p>
    </div>
    <RepositorySubmitForm v-model="githubUrl" :pending="pending" :error="error" @submit="submit" />
  </section>
</template>
```

```vue
<script setup lang="ts">
defineProps<{
  taskId?: string
}>()
</script>

<template>
  <section class="panel">
    <h2>Task detail workbench is coming next</h2>
    <p>This temporary shell keeps the router valid until the task detail page is implemented.</p>
  </section>
</template>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Set-Location web; npm test -- --run src/components/RepositorySubmitForm.spec.ts src/pages/HomePage.spec.ts`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add web/src/router/index.ts web/src/pages/HomePage.vue web/src/pages/TaskDetailPage.vue web/src/components/RepositorySubmitForm.vue web/src/pages/HomePage.spec.ts web/src/components/RepositorySubmitForm.spec.ts
git commit -m "feat: add repository submission workflow"
```

### Task 4: Build reusable task display components

**Files:**
- Create: `web/src/components/TaskStatusCard.vue`
- Create: `web/src/components/TaskEventTimeline.vue`
- Create: `web/src/components/ResultSectionCard.vue`
- Create: `web/src/components/AnalysisResultView.vue`
- Create: `web/src/components/TaskErrorState.vue`
- Test: `web/src/components/TaskStatusCard.spec.ts`
- Test: `web/src/components/TaskEventTimeline.spec.ts`
- Test: `web/src/components/AnalysisResultView.spec.ts`
- Test: `web/src/components/TaskErrorState.spec.ts`

- [ ] **Step 1: Write the failing component tests**

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskStatusCard from './TaskStatusCard.vue'

describe('TaskStatusCard', () => {
  it('renders state, stage, and progress', () => {
    const wrapper = mount(TaskStatusCard, {
      props: {
        status: {
          task_id: 'task-1',
          state: 'running',
          stage: 'detect_stack',
          progress: 35,
          message: null,
          error: null,
          created_at: '2026-04-06T10:00:00Z',
          updated_at: '2026-04-06T10:01:00Z',
        },
      },
    })

    expect(wrapper.text()).toContain('running')
    expect(wrapper.text()).toContain('detect_stack')
    expect(wrapper.text()).toContain('35%')
  })
})
```

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskEventTimeline from './TaskEventTimeline.vue'

describe('TaskEventTimeline', () => {
  it('renders ordered event entries', () => {
    const wrapper = mount(TaskEventTimeline, {
      props: {
        events: [
          { stage: 'fetch_repo', progress: 5 },
          { stage: 'scan_tree', progress: 20 },
        ],
      },
    })

    expect(wrapper.text()).toContain('fetch_repo')
    expect(wrapper.text()).toContain('scan_tree')
  })
})
```

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AnalysisResultView from './AnalysisResultView.vue'

describe('AnalysisResultView', () => {
  it('renders stack and backend routes', () => {
    const wrapper = mount(AnalysisResultView, {
      props: {
        result: {
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          repo_summary: { name: 'Hello-World', files: ['app/main.py'], key_files: ['app/main.py'], file_count: 1 },
          detected_stack: { frameworks: ['fastapi', 'vue'], languages: ['py', 'ts'] },
          backend_summary: { routes: [{ method: 'GET', path: '/health', source_file: 'app/main.py' }] },
          frontend_summary: { routing: [], api_calls: [] },
          logic_summary: { flows: [] },
          tutorial_summary: { mental_model: 'A simple flow', run_steps: ['uvicorn app.main:app'], pitfalls: ['Redis offline'], self_check_questions: ['What runs first?'] },
          mermaid_sections: { system: 'graph TD\\nA-->B' },
        },
      },
    })

    expect(wrapper.text()).toContain('fastapi')
    expect(wrapper.text()).toContain('/health')
  })
})
```

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskErrorState from './TaskErrorState.vue'

describe('TaskErrorState', () => {
  it('renders the provided title and message', () => {
    const wrapper = mount(TaskErrorState, {
      props: {
        title: 'Task failed',
        message: 'Repository clone failed.',
      },
    })

    expect(wrapper.text()).toContain('Task failed')
    expect(wrapper.text()).toContain('Repository clone failed.')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Set-Location web; npm test -- --run src/components/TaskStatusCard.spec.ts src/components/TaskEventTimeline.spec.ts src/components/AnalysisResultView.spec.ts src/components/TaskErrorState.spec.ts`
Expected: fail because the UI components do not exist yet

- [ ] **Step 3: Write the minimal display components**

```vue
<script setup lang="ts">
import type { TaskStatus } from '../types/contracts'

defineProps<{
  status: TaskStatus
}>()
</script>

<template>
  <section class="panel status-card">
    <p class="status-card__label">Task {{ status.task_id }}</p>
    <h3>{{ status.state }}</h3>
    <p>Stage: {{ status.stage ?? 'waiting' }}</p>
    <p>Progress: {{ status.progress }}%</p>
    <p v-if="status.message">{{ status.message }}</p>
    <p v-else-if="status.error" class="status-card__error">{{ status.error }}</p>
  </section>
</template>
```

```vue
<script setup lang="ts">
import type { TaskStreamEvent } from '../types/contracts'

defineProps<{
  events: TaskStreamEvent[]
}>()
</script>

<template>
  <section class="panel timeline">
    <h3>Task Timeline</h3>
    <ol>
      <li v-for="(event, index) in events" :key="`${event.stage ?? 'event'}-${index}`">
        <strong>{{ event.stage ?? 'update' }}</strong>
        <span v-if="event.progress !== undefined"> {{ event.progress }}%</span>
        <span v-if="event.message"> - {{ event.message }}</span>
        <span v-if="event.error"> - {{ event.error }}</span>
      </li>
    </ol>
  </section>
</template>
```

```vue
<template>
  <section class="panel result-card">
    <header class="result-card__header">
      <p class="result-card__eyebrow">{{ eyebrow }}</p>
      <h3>{{ title }}</h3>
    </header>
    <div class="result-card__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  eyebrow?: string
}>()
</script>
```

```vue
<script setup lang="ts">
import type { AnalysisResult } from '../types/contracts'

import ResultSectionCard from './ResultSectionCard.vue'

defineProps<{
  result: AnalysisResult
}>()
</script>

<template>
  <div class="result-grid">
    <ResultSectionCard title="Project Overview" eyebrow="Repository">
      <p>{{ result.repo_summary.name }}</p>
      <p>{{ result.github_url }}</p>
    </ResultSectionCard>

    <ResultSectionCard title="Detected Tech Stack" eyebrow="Stack">
      <ul>
        <li v-for="framework in result.detected_stack.frameworks" :key="framework">{{ framework }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Backend Analysis" eyebrow="Routes">
      <ul>
        <li v-for="route in result.backend_summary.routes" :key="`${route.method}-${route.path}`">
          {{ route.method }} {{ route.path }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Frontend Analysis" eyebrow="Calls">
      <ul>
        <li v-for="call in result.frontend_summary.api_calls" :key="`${call.source_file}-${call.url}`">
          {{ call.url }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Core Logic Flows" eyebrow="Inference">
      <ul>
        <li v-for="flow in result.logic_summary.flows" :key="`${flow.frontend_call}-${flow.backend_route}`">
          {{ flow.frontend_call }} -> {{ flow.backend_method }} {{ flow.backend_route }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Beginner Learning Guide" eyebrow="Tutor">
      <p>{{ result.tutorial_summary.mental_model }}</p>
      <ul>
        <li v-for="step in result.tutorial_summary.run_steps" :key="step">{{ step }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Markdown Output" eyebrow="Artifact">
      <pre>{{ result.markdown_path }}</pre>
      <pre>{{ result.mermaid_sections.system }}</pre>
    </ResultSectionCard>
  </div>
</template>
```

```vue
<script setup lang="ts">
defineProps<{
  title: string
  message: string
}>()
</script>

<template>
  <section class="panel error-panel">
    <h3>{{ title }}</h3>
    <p>{{ message }}</p>
  </section>
</template>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Set-Location web; npm test -- --run src/components/TaskStatusCard.spec.ts src/components/TaskEventTimeline.spec.ts src/components/AnalysisResultView.spec.ts src/components/TaskErrorState.spec.ts`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add web/src/components/TaskStatusCard.vue web/src/components/TaskEventTimeline.vue web/src/components/ResultSectionCard.vue web/src/components/AnalysisResultView.vue web/src/components/TaskErrorState.vue web/src/components/TaskStatusCard.spec.ts web/src/components/TaskEventTimeline.spec.ts web/src/components/AnalysisResultView.spec.ts web/src/components/TaskErrorState.spec.ts
git commit -m "feat: add task and result display components"
```

### Task 5: Add composables for status polling, SSE, and result loading

**Files:**
- Create: `web/src/composables/useTaskStatus.ts`
- Create: `web/src/composables/useTaskStream.ts`
- Create: `web/src/composables/useAnalysisResult.ts`
- Test: `web/src/composables/useTaskStatus.spec.ts`
- Test: `web/src/composables/useTaskStream.spec.ts`
- Test: `web/src/composables/useAnalysisResult.spec.ts`

- [ ] **Step 1: Write the failing composable tests**

```ts
import { describe, expect, it, vi } from 'vitest'

import { useTaskStatus } from './useTaskStatus'

describe('useTaskStatus', () => {
  it('loads the current task status', async () => {
    const fetchStatus = vi.fn().mockResolvedValue({
      task_id: 'task-1',
      state: 'running',
      stage: 'scan_tree',
      progress: 20,
      message: null,
      error: null,
      created_at: '2026-04-06T10:00:00Z',
      updated_at: '2026-04-06T10:01:00Z',
    })

    const model = useTaskStatus('task-1', fetchStatus)
    await model.refresh()

    expect(model.status.value?.stage).toBe('scan_tree')
  })
})
```

```ts
import { describe, expect, it, vi } from 'vitest'

import { useTaskStream } from './useTaskStream'

describe('useTaskStream', () => {
  it('appends incoming stream events', () => {
    let emit: ((event: { stage?: string }) => void) | undefined

    const open = vi.fn((_url: string, onEvent: (event: { stage?: string }) => void) => {
      emit = onEvent
      return { close: vi.fn(), onerror: null }
    })

    const model = useTaskStream('/api/v1/tasks/task-1/stream', open)
    model.connect()
    emit?.({ stage: 'detect_stack' })

    expect(model.events.value).toHaveLength(1)
    expect(model.events.value[0].stage).toBe('detect_stack')
  })
})
```

```ts
import { describe, expect, it, vi } from 'vitest'

import { useAnalysisResult } from './useAnalysisResult'

describe('useAnalysisResult', () => {
  it('stores a successful result payload', async () => {
    const fetchResult = vi.fn().mockResolvedValue({
      kind: 'success',
      data: { github_url: 'https://github.com/octocat/Hello-World' },
    })

    const model = useAnalysisResult('task-1', fetchResult as never)
    await model.load()

    expect(model.result.value?.github_url).toContain('github.com')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Set-Location web; npm test -- --run src/composables/useTaskStatus.spec.ts src/composables/useTaskStream.spec.ts src/composables/useAnalysisResult.spec.ts`
Expected: fail because the composables do not exist yet

- [ ] **Step 3: Write the minimal composable implementation**

```ts
import { onBeforeUnmount, ref } from 'vue'

import { fetchTaskStatus } from '../services/api'
import type { TaskStatus } from '../types/contracts'

export function useTaskStatus(
  taskId: string,
  loader: typeof fetchTaskStatus = fetchTaskStatus,
  pollMs = 4000,
) {
  const status = ref<TaskStatus | null>(null)
  const loading = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  async function refresh() {
    loading.value = true
    try {
      status.value = await loader(taskId)
    } finally {
      loading.value = false
    }
  }

  function startPolling() {
    stopPolling()
    timer = setInterval(() => {
      void refresh()
    }, pollMs)
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onBeforeUnmount(stopPolling)

  return {
    status,
    loading,
    refresh,
    startPolling,
    stopPolling,
  }
}
```

```ts
import { onBeforeUnmount, ref } from 'vue'

import { openTaskStream } from '../services/stream'
import type { TaskStreamEvent } from '../types/contracts'

export function useTaskStream(
  url: string,
  opener: typeof openTaskStream = openTaskStream,
) {
  const events = ref<TaskStreamEvent[]>([])
  const connected = ref(false)
  let source: Pick<EventSource, 'close' | 'onerror'> | null = null

  function connect() {
    source = opener(url, (event) => {
      events.value.push(event)
    })
    connected.value = true
    source.onerror = () => {
      connected.value = false
    }
  }

  function disconnect() {
    source?.close()
    source = null
    connected.value = false
  }

  onBeforeUnmount(disconnect)

  return {
    events,
    connected,
    connect,
    disconnect,
  }
}
```

```ts
import { ref } from 'vue'

import { fetchTaskResult } from '../services/api'
import type { AnalysisResult, TaskResultResponse } from '../types/contracts'

export function useAnalysisResult(
  taskId: string,
  loader: typeof fetchTaskResult = fetchTaskResult,
) {
  const result = ref<AnalysisResult | null>(null)
  const pending = ref(false)
  const terminalError = ref('')
  const notFound = ref(false)

  async function load() {
    pending.value = true
    terminalError.value = ''
    notFound.value = false

    try {
      const payload = (await loader(taskId)) as TaskResultResponse
      if (payload.kind === 'success') {
        result.value = payload.data
        return
      }
      if (payload.kind === 'failed') {
        terminalError.value = payload.error ?? `Task ended in state ${payload.state}.`
        return
      }
      result.value = null
    } catch (cause) {
      const error = cause instanceof Error ? cause.message : 'Result loading failed.'
      if (error.includes('404')) {
        notFound.value = true
      } else {
        terminalError.value = error
      }
    } finally {
      pending.value = false
    }
  }

  return {
    result,
    pending,
    terminalError,
    notFound,
    load,
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Set-Location web; npm test -- --run src/composables/useTaskStatus.spec.ts src/composables/useTaskStream.spec.ts src/composables/useAnalysisResult.spec.ts`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add web/src/composables/useTaskStatus.ts web/src/composables/useTaskStream.ts web/src/composables/useAnalysisResult.ts web/src/composables/useTaskStatus.spec.ts web/src/composables/useTaskStream.spec.ts web/src/composables/useAnalysisResult.spec.ts
git commit -m "feat: add task orchestration composables"
```

### Task 6: Build the task detail page and wire the full workbench flow

**Files:**
- Create: `web/src/pages/TaskDetailPage.vue`
- Modify: `web/src/components/AnalysisResultView.vue`
- Test: `web/src/pages/TaskDetailPage.spec.ts`
- Test: `web/src/pages/HomePage.spec.ts`

- [ ] **Step 1: Write the failing task detail page tests**

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import TaskDetailPage from './TaskDetailPage.vue'

vi.mock('../composables/useTaskStatus', () => ({
  useTaskStatus: () => ({
    status: { value: { task_id: 'task-1', state: 'succeeded', stage: 'finalize', progress: 100, message: null, error: null, created_at: '2026-04-06T10:00:00Z', updated_at: '2026-04-06T10:10:00Z' } },
    loading: { value: false },
    refresh: vi.fn().mockResolvedValue(undefined),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
  }),
}))

vi.mock('../composables/useTaskStream', () => ({
  useTaskStream: () => ({
    events: { value: [{ stage: 'scan_tree', progress: 20 }] },
    connected: { value: true },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

vi.mock('../composables/useAnalysisResult', () => ({
  useAnalysisResult: () => ({
    result: {
      value: {
        github_url: 'https://github.com/octocat/Hello-World',
        repo_path: 'artifacts/task-1/repo',
        markdown_path: 'artifacts/task-1/result.md',
        repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
        detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
        backend_summary: { routes: [] },
        frontend_summary: { routing: [], api_calls: [] },
        logic_summary: { flows: [] },
        tutorial_summary: { mental_model: 'Simple flow', run_steps: [], pitfalls: [], self_check_questions: [] },
        mermaid_sections: { system: 'graph TD\\nA-->B' },
      },
    },
    pending: { value: false },
    terminalError: { value: '' },
    notFound: { value: false },
    load: vi.fn().mockResolvedValue(undefined),
  }),
}))

describe('TaskDetailPage', () => {
  it('renders status, timeline, and result sections', async () => {
    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-1',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('task-1')
    expect(wrapper.text()).toContain('scan_tree')
    expect(wrapper.text()).toContain('Hello-World')
  })
})
```

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import HomePage from './HomePage.vue'
import TaskDetailPage from './TaskDetailPage.vue'

vi.mock('../services/api', () => ({
  createAnalysisTask: vi.fn().mockResolvedValue({
    task_id: 'task-11',
    status_url: '/api/v1/tasks/task-11',
    result_url: '/api/v1/tasks/task-11/result',
    stream_url: '/api/v1/tasks/task-11/stream',
  }),
}))

describe('submission flow', () => {
  it('lands on the task detail route after submission', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomePage },
        { path: '/tasks/:taskId', component: TaskDetailPage, props: true },
      ],
    })

    router.push('/')
    await router.isReady()

    const wrapper = mount(HomePage, {
      global: {
        plugins: [router],
      },
    })

    await wrapper.get('input').setValue('https://github.com/octocat/Hello-World')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(router.currentRoute.value.params.taskId).toBe('task-11')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Set-Location web; npm test -- --run src/pages/TaskDetailPage.spec.ts src/pages/HomePage.spec.ts`
Expected: fail because the existing task detail page stub does not yet render the full status, timeline, and result workbench

- [ ] **Step 3: Write the minimal task workbench page implementation**

```vue
<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'

import AnalysisResultView from '../components/AnalysisResultView.vue'
import TaskErrorState from '../components/TaskErrorState.vue'
import TaskEventTimeline from '../components/TaskEventTimeline.vue'
import TaskStatusCard from '../components/TaskStatusCard.vue'
import { useAnalysisResult } from '../composables/useAnalysisResult'
import { useTaskStatus } from '../composables/useTaskStatus'
import { useTaskStream } from '../composables/useTaskStream'

const props = defineProps<{
  taskId: string
}>()

const statusModel = useTaskStatus(props.taskId)
const streamModel = useTaskStream(`/api/v1/tasks/${props.taskId}/stream`)
const resultModel = useAnalysisResult(props.taskId)

const isSucceeded = computed(() => statusModel.status.value?.state === 'succeeded')
const isFailed = computed(() => {
  const state = statusModel.status.value?.state
  return state === 'failed' || state === 'cancelled'
})

onMounted(async () => {
  await statusModel.refresh()
  statusModel.startPolling()
  streamModel.connect()
})

watch(isSucceeded, async (value) => {
  if (value) {
    await resultModel.load()
    statusModel.stopPolling()
  }
}, { immediate: true })
</script>

<template>
  <div class="task-layout">
    <TaskErrorState
      v-if="resultModel.notFound"
      title="Task not found"
      message="The requested task does not exist or has already been removed."
    />

    <template v-else>
      <TaskStatusCard v-if="statusModel.status" :status="statusModel.status" />

      <TaskEventTimeline :events="streamModel.events" />

      <TaskErrorState
        v-if="isFailed && statusModel.status?.error"
        title="Task failed"
        :message="statusModel.status.error"
      />

      <section v-else-if="resultModel.pending" class="panel">
        <h3>Result loading</h3>
        <p>The task is complete, but the final result payload is still being fetched.</p>
      </section>

      <AnalysisResultView v-else-if="resultModel.result" :result="resultModel.result" />
    </template>
  </div>
</template>
```

```vue
<template>
  <div class="result-grid">
    <ResultSectionCard title="Project Overview" eyebrow="Repository">
      <p>{{ result.repo_summary.name }}</p>
      <p>{{ result.github_url }}</p>
    </ResultSectionCard>

    <ResultSectionCard title="Detected Tech Stack" eyebrow="Stack">
      <ul>
        <li v-for="framework in result.detected_stack.frameworks" :key="framework">{{ framework }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Backend Analysis" eyebrow="Routes">
      <ul>
        <li v-for="route in result.backend_summary.routes" :key="`${route.method}-${route.path}`">
          {{ route.method }} {{ route.path }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Frontend Analysis" eyebrow="Calls">
      <ul>
        <li v-for="call in result.frontend_summary.api_calls" :key="`${call.source_file}-${call.url}`">
          {{ call.url }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Core Logic Flows" eyebrow="Inference">
      <ul>
        <li v-for="flow in result.logic_summary.flows" :key="`${flow.frontend_call}-${flow.backend_route}`">
          {{ flow.frontend_call }} -> {{ flow.backend_method }} {{ flow.backend_route }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Beginner Learning Guide" eyebrow="Tutor">
      <p>{{ result.tutorial_summary.mental_model }}</p>
      <ul>
        <li v-for="step in result.tutorial_summary.run_steps" :key="step">{{ step }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Markdown Artifact Path" eyebrow="Artifact">
      <pre>{{ result.markdown_path }}</pre>
    </ResultSectionCard>

    <ResultSectionCard title="System Diagram Source" eyebrow="Mermaid">
      <pre>{{ result.mermaid_sections.system }}</pre>
    </ResultSectionCard>
  </div>
</template>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Set-Location web; npm test -- --run src/pages/TaskDetailPage.spec.ts src/pages/HomePage.spec.ts`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/TaskDetailPage.vue web/src/pages/TaskDetailPage.spec.ts web/src/pages/HomePage.spec.ts web/src/components/AnalysisResultView.vue
git commit -m "feat: add task workbench page"
```

### Task 7: Finish frontend integration, docs, and full verification

**Files:**
- Modify: `README.md`
- Modify: `web/src/assets/base.css`
- Modify: `web/src/pages/TaskDetailPage.vue`
- Modify: `web/src/components/AnalysisResultView.vue`
- Test: `web/src/components/AnalysisResultView.spec.ts`
- Test: `web/src/pages/TaskDetailPage.spec.ts`

- [ ] **Step 1: Write the failing integration polish tests**

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AnalysisResultView from './AnalysisResultView.vue'

describe('AnalysisResultView markdown output', () => {
  it('renders the markdown artifact path and diagram source separately', () => {
    const wrapper = mount(AnalysisResultView, {
      props: {
        result: {
          github_url: 'https://github.com/octocat/Hello-World',
          repo_path: 'artifacts/task-1/repo',
          markdown_path: 'artifacts/task-1/result.md',
          repo_summary: { name: 'Hello-World', files: [], key_files: [], file_count: 0 },
          detected_stack: { frameworks: ['fastapi'], languages: ['py'] },
          backend_summary: { routes: [] },
          frontend_summary: { routing: [], api_calls: [] },
          logic_summary: { flows: [] },
          tutorial_summary: { mental_model: 'Simple flow', run_steps: [], pitfalls: [], self_check_questions: [] },
          mermaid_sections: { system: 'graph TD\\nA-->B' },
        },
      },
    })

    expect(wrapper.text()).toContain('Markdown Artifact Path')
    expect(wrapper.text()).toContain('System Diagram Source')
  })
})
```

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import TaskDetailPage from './TaskDetailPage.vue'

vi.mock('../composables/useTaskStatus', () => ({
  useTaskStatus: () => ({
    status: { value: { task_id: 'task-2', state: 'failed', stage: 'finalize', progress: 100, message: null, error: 'clone failed', created_at: '2026-04-06T10:00:00Z', updated_at: '2026-04-06T10:10:00Z' } },
    loading: { value: false },
    refresh: vi.fn().mockResolvedValue(undefined),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
  }),
}))

vi.mock('../composables/useTaskStream', () => ({
  useTaskStream: () => ({
    events: { value: [{ stage: 'fetch_repo', progress: 5, error: 'clone failed' }] },
    connected: { value: false },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

vi.mock('../composables/useAnalysisResult', () => ({
  useAnalysisResult: () => ({
    result: { value: null },
    pending: { value: false },
    terminalError: { value: 'clone failed' },
    notFound: { value: false },
    load: vi.fn().mockResolvedValue(undefined),
  }),
}))

describe('TaskDetailPage failed state', () => {
  it('renders a terminal failure message', async () => {
    const wrapper = mount(TaskDetailPage, {
      props: {
        taskId: 'task-2',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Task failed')
    expect(wrapper.text()).toContain('clone failed')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Set-Location web; npm test -- --run src/components/AnalysisResultView.spec.ts src/pages/TaskDetailPage.spec.ts`
Expected: fail until the final result split and failed-state UI are finished cleanly

- [ ] **Step 3: Finish the final frontend polish and developer docs**

```vue
<template>
  <div class="result-grid">
    <ResultSectionCard title="Project Overview" eyebrow="Repository">
      <p>{{ result.repo_summary.name }}</p>
      <p>{{ result.github_url }}</p>
      <p>{{ result.repo_summary.file_count }} files scanned</p>
    </ResultSectionCard>

    <ResultSectionCard title="Detected Tech Stack" eyebrow="Stack">
      <ul>
        <li v-for="framework in result.detected_stack.frameworks" :key="framework">{{ framework }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Backend Analysis" eyebrow="Routes">
      <ul>
        <li v-for="route in result.backend_summary.routes" :key="`${route.method}-${route.path}`">
          {{ route.method }} {{ route.path }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Frontend Analysis" eyebrow="Calls">
      <ul>
        <li v-for="call in result.frontend_summary.api_calls" :key="`${call.source_file}-${call.url}`">
          {{ call.url }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Core Logic Flows" eyebrow="Inference">
      <ul>
        <li v-for="flow in result.logic_summary.flows" :key="`${flow.frontend_call}-${flow.backend_route}`">
          {{ flow.frontend_call }} -> {{ flow.backend_method }} {{ flow.backend_route }}
        </li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Beginner Learning Guide" eyebrow="Tutor">
      <p>{{ result.tutorial_summary.mental_model }}</p>
      <ul>
        <li v-for="step in result.tutorial_summary.run_steps" :key="step">{{ step }}</li>
      </ul>
    </ResultSectionCard>

    <ResultSectionCard title="Markdown Artifact Path" eyebrow="Artifact">
      <pre>{{ result.markdown_path }}</pre>
    </ResultSectionCard>

    <ResultSectionCard title="System Diagram Source" eyebrow="Mermaid">
      <pre>{{ result.mermaid_sections.system }}</pre>
    </ResultSectionCard>
  </div>
</template>
```

```vue
<template>
  <div class="task-layout">
    <TaskStatusCard v-if="statusModel.status" :status="statusModel.status" />

    <section class="task-layout__meta panel">
      <p>Live stream: {{ streamModel.connected ? 'connected' : 'disconnected' }}</p>
      <p>Task ID: {{ taskId }}</p>
    </section>

    <TaskEventTimeline :events="streamModel.events" />

    <TaskErrorState
      v-if="resultModel.notFound"
      title="Task not found"
      message="The requested task does not exist or has already been removed."
    />

    <TaskErrorState
      v-else-if="isFailed"
      title="Task failed"
      :message="statusModel.status?.error ?? resultModel.terminalError ?? 'Task ended without a result.'"
    />

    <section v-else-if="!resultModel.result" class="panel">
      <h3>Result pending</h3>
      <p>Waiting for the backend to finish writing the final analysis payload.</p>
    </section>

    <AnalysisResultView v-else :result="resultModel.result" />
  </div>
</template>
```

```css
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 24px;
  box-shadow: var(--shadow);
  padding: 20px;
}

.hero-panel,
.task-layout {
  display: grid;
  gap: 20px;
}

.hero-panel {
  grid-template-columns: 1.2fr 1fr;
  align-items: start;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.submit-form__input,
.submit-form__button {
  width: 100%;
  border-radius: 16px;
  border: 1px solid var(--border);
  padding: 14px 16px;
  font: inherit;
}

.submit-form__button {
  background: var(--accent);
  color: white;
  cursor: pointer;
}

.submit-form__button:disabled {
  cursor: not-allowed;
  background: #9bb7ae;
}

.submit-form__error,
.status-card__error {
  color: var(--danger);
}

pre {
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 900px) {
  .hero-panel,
  .result-grid {
    grid-template-columns: 1fr;
  }
}
```

````markdown
# GitHub Tech Doc Generator

Backend-first MVP for generating technical documentation from a GitHub repository, now with a Vue frontend workbench.

## Backend setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d redis
uvicorn app.main:app --reload
```

Start the worker in a second terminal:

```powershell
arq app.tasks.worker.WorkerSettings
```

## Frontend setup

```powershell
Set-Location web
npm install
npm run dev
```

The frontend dev server proxies `/api` requests to `http://127.0.0.1:8000`.

## Test

```powershell
python -m pytest
Set-Location web
npm test -- --run
npm run build
```
````

- [ ] **Step 4: Run the full frontend and backend verification**

Run: `python -m pytest`
Expected: backend tests still pass

Run: `Set-Location web; npm test -- --run`
Expected: all frontend tests pass

Run: `Set-Location web; npm run build`
Expected: Vite production build completes without errors

- [ ] **Step 5: Commit**

```bash
git add README.md web/src/assets/base.css web/src/pages/TaskDetailPage.vue web/src/components/AnalysisResultView.vue web/src/components/AnalysisResultView.spec.ts web/src/pages/TaskDetailPage.spec.ts
git commit -m "feat: finish vue task workbench"
```

## Self-Review

### Spec coverage

- Standalone Vue app under `web/`: Tasks 1 and 2
- Two-page flow with `/` and `/tasks/:taskId`: Tasks 3 and 6
- Status, SSE timeline, and result display: Tasks 4, 5, and 6
- Responsive engineering-tool UI direction: Tasks 1 and 7
- TDD for components, pages, services, and composables: all tasks
- Root developer docs and local run flow: Task 7

### Red-Flag Scan

- No unresolved marker tokens remain in the task steps
- Each task includes explicit files, tests, commands, and commit steps
- Each task starts with a failing test before implementation code

### Type consistency

- Frontend contracts match the current backend endpoints under `/api/v1/tasks/...`
- `AnalysisResult` fields align to the current backend `app/core/models.py` structure
- SSE events are treated as optional-field payloads because current backend events are sparse but consistent with that union
