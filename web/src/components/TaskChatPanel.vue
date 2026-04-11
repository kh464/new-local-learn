<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { fetchTaskChatMessages, submitTaskQuestion } from '../services/api'
import type { TaskChatMessage, TaskGraphEvidence, TaskStatus } from '../types/contracts'

const props = defineProps<{
  taskId: string
  status?: TaskStatus | null
}>()

const messages = ref<TaskChatMessage[]>([])
const question = ref('')
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const activeCitationPathsByMessage = ref<Record<string, string[]>>({})

const knowledgeState = computed(() => props.status?.knowledge_state ?? 'pending')
const knowledgeError = computed(() => props.status?.knowledge_error ?? '')
const isKnowledgeReady = computed(() => knowledgeState.value === 'ready')
const isKnowledgeBuilding = computed(() => knowledgeState.value === 'running' || props.status?.stage === 'build_knowledge')
const isKnowledgeFailed = computed(() => knowledgeState.value === 'failed')
const emptyStatusText = computed(() => {
  if (isKnowledgeBuilding.value) {
    return '知识库构建中，完成后即可继续针对代码提问。'
  }
  if (isKnowledgeFailed.value) {
    return '知识库构建失败，当前无法继续代码问答。'
  }
  if (isKnowledgeReady.value) {
    return '知识库已就绪，可以继续提问代码结构、调用链、接口映射和实现细节。'
  }
  return '知识库尚未就绪，请稍后再试。'
})
const canSubmit = computed(() => isKnowledgeReady.value && !sending.value && question.value.trim().length > 0)

type CallChainStep = {
  key: string
  title: string
  value: string
}

const SOURCE_FILE_PATTERN = /[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|vue)/g

function formatAnswerSource(source?: 'llm' | 'local' | null): string {
  if (source === 'llm') {
    return '回答：大模型'
  }
  if (source === 'local') {
    return '回答：本地'
  }
  return ''
}

function formatPlanningSource(source?: string | null): string {
  if (source === 'llm') {
    return '规划：大模型'
  }
  if (source === 'rule') {
    return '规划：规则兜底'
  }
  return ''
}

function renderAnswerSource(source?: 'llm' | 'local' | null): string {
  if (source === 'llm') {
    return 'LLM 回答'
  }
  if (source === 'local') {
    return '本地知识库'
  }
  return ''
}

function renderPlanningSource(source?: string | null): string {
  if (source === 'llm') {
    return 'LLM 规划'
  }
  if (source === 'rule') {
    return '规则规划'
  }
  return ''
}

function hasPlannerDebug(message: TaskChatMessage): boolean {
  return Boolean(
    message.planner_metadata?.search_queries?.length ||
      message.answer_debug?.confirmed_facts?.length ||
      message.answer_debug?.evidence_gaps?.length,
  )
}

function groupGraphEvidence(graphEvidence?: TaskGraphEvidence[]) {
  const evidence = graphEvidence ?? []
  return {
    entrypoints: evidence.filter((item) => item.kind === 'entrypoint'),
    callChains: evidence.filter((item) => item.kind === 'call_chain'),
    symbols: evidence.filter((item) => item.kind === 'symbol'),
    edges: evidence.filter((item) => item.kind === 'edge'),
  }
}

function parseCallChain(label: string): CallChainStep[] {
  const segments = label
    .split('->')
    .map((segment) => segment.trim())
    .filter(Boolean)

  if (segments.length < 3) {
    return []
  }

  const routeIndex = segments.findIndex((segment) => /^(GET|POST|PUT|DELETE|PATCH)\s+\//.test(segment))
  if (routeIndex < 1 || routeIndex + 1 >= segments.length) {
    return []
  }

  const frontendSegments = segments.slice(0, routeIndex)
  const routeSegment = segments[routeIndex]
  const backendSegments = segments.slice(routeIndex + 1)
  const steps: CallChainStep[] = []

  if (frontendSegments.length >= 2 && /main\.(ts|js|tsx|jsx)$/.test(frontendSegments[0])) {
    steps.push({
      key: 'page-entry',
      title: '页面入口',
      value: frontendSegments[0],
    })
  }

  const handlerMatch = frontendSegments.at(-1)?.match(
    /^(?<target>.+?):(?<handler>[A-Za-z_][A-Za-z0-9_]*)(?: \[(?<trigger>[^\]]+)\])?$/,
  )

  const componentChain = frontendSegments.slice(steps.length ? 1 : 0, handlerMatch ? -1 : undefined)
  if (componentChain.length) {
    steps.push({
      key: 'component-chain',
      title: '组件链',
      value: componentChain.join(' -> '),
    })
  }

  if (handlerMatch?.groups) {
    const trigger = handlerMatch.groups.trigger ? ` [${handlerMatch.groups.trigger}]` : ''
    steps.push({
      key: 'frontend-handler',
      title: '交互函数',
      value: `${handlerMatch.groups.target}:${handlerMatch.groups.handler}${trigger}`,
    })
  } else if (frontendSegments.length) {
    steps.push({
      key: 'frontend-file',
      title: '前端文件',
      value: frontendSegments.at(-1) ?? '',
    })
  }

  steps.push({
    key: 'route',
    title: '接口路由',
    value: routeSegment,
  })

  steps.push({
    key: 'backend-handler',
    title: '后端处理',
    value: backendSegments[0],
  })

  if (backendSegments.length > 1) {
    steps.push({
      key: 'backend-followup',
      title: '后续调用',
      value: backendSegments.slice(1).join(' -> '),
    })
  }

  return steps
}

function extractPathsFromText(value: string): string[] {
  return Array.from(new Set(value.match(SOURCE_FILE_PATTERN) ?? []))
}

function resolveStepCitationPaths(step: CallChainStep, fallbackPath?: string | null): string[] {
  const paths = extractPathsFromText(step.value)
  if (paths.length) {
    return paths
  }
  if (fallbackPath) {
    return [fallbackPath]
  }
  return []
}

function toggleStepHighlight(messageId: string, step: CallChainStep, fallbackPath?: string | null) {
  const nextPaths = resolveStepCitationPaths(step, fallbackPath)
  const currentPaths = activeCitationPathsByMessage.value[messageId] ?? []
  const isSameSelection =
    currentPaths.length === nextPaths.length && currentPaths.every((path, index) => path === nextPaths[index])

  activeCitationPathsByMessage.value = {
    ...activeCitationPathsByMessage.value,
    [messageId]: isSameSelection ? [] : nextPaths,
  }
}

function isCitationHighlighted(messageId: string, citationPath: string): boolean {
  const activePaths = activeCitationPathsByMessage.value[messageId] ?? []
  if (!activePaths.length) {
    return false
  }
  return activePaths.includes(citationPath)
}

function isStepSelected(messageId: string, step: CallChainStep, fallbackPath?: string | null): boolean {
  const activePaths = activeCitationPathsByMessage.value[messageId] ?? []
  const stepPaths = resolveStepCitationPaths(step, fallbackPath)
  if (!activePaths.length || !stepPaths.length || activePaths.length !== stepPaths.length) {
    return false
  }
  return activePaths.every((path, index) => path === stepPaths[index])
}

async function loadMessages() {
  if (!isKnowledgeReady.value) {
    messages.value = []
    loading.value = false
    return
  }

  loading.value = true
  error.value = ''
  try {
    const payload = await fetchTaskChatMessages(props.taskId)
    messages.value = payload.messages
    activeCitationPathsByMessage.value = {}
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '问答记录加载失败。'
  } finally {
    loading.value = false
  }
}

async function handleSubmit() {
  const trimmed = question.value.trim()
  if (!trimmed || !isKnowledgeReady.value || sending.value) {
    return
  }

  sending.value = true
  error.value = ''
  try {
    const exchange = await submitTaskQuestion(props.taskId, trimmed)
    messages.value = [...messages.value, exchange.user_message, exchange.assistant_message]
    activeCitationPathsByMessage.value = {}
    question.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '提问失败。'
  } finally {
    sending.value = false
  }
}

watch(
  () => [props.taskId, knowledgeState.value] as const,
  async () => {
    await loadMessages()
  },
  { immediate: true },
)
</script>

<template>
  <aside class="task-chat panel">
    <div class="task-chat__header">
      <div>
        <p class="task-chat__eyebrow">代码问答</p>
        <h3>继续追问仓库实现</h3>
      </div>
      <p class="task-chat__hint">回答会优先依据仓库认知图与真实代码理解，展示调用链和文件位置。</p>
    </div>

    <div v-if="isKnowledgeBuilding" class="task-chat__state task-chat__state--building">
      <strong>知识库构建中</strong>
      <p>系统正在整理仓库认知图，完成后会自动开放问答。</p>
    </div>

    <div v-else-if="isKnowledgeFailed" class="task-chat__state task-chat__state--failed">
      <strong>知识库构建失败</strong>
      <p>{{ knowledgeError || '本次任务的知识库未能成功生成，因此当前不能继续代码问答。' }}</p>
    </div>

    <p v-if="loading" class="task-chat__status">正在加载历史问答...</p>
    <p v-else-if="!messages.length" class="task-chat__status">{{ emptyStatusText }}</p>
    <p v-if="error" class="task-chat__error">{{ error }}</p>

    <div class="task-chat__messages">
      <article
        v-for="message in messages"
        :key="message.message_id"
        class="task-chat__message"
        :class="`task-chat__message--${message.role}`"
      >
        <div class="task-chat__message-header">
          <p class="task-chat__role">{{ message.role === 'user' ? '用户' : 'Agent' }}</p>
          <div class="task-chat__meta-badges">
            <span v-if="message.answer_source" class="task-chat__badge task-chat__badge--source">
              {{ renderAnswerSource(message.answer_source) }}
            </span>
            <span
              v-if="message.role === 'assistant' && message.planner_metadata?.planning_source"
              class="task-chat__badge task-chat__badge--planner"
            >
              {{ renderPlanningSource(message.planner_metadata.planning_source) }}
            </span>
            <span v-if="message.confidence" class="task-chat__confidence">
              置信度：{{ message.confidence }}
            </span>
          </div>
        </div>

        <p class="task-chat__content">{{ message.content }}</p>

        <div
          v-if="message.role === 'assistant' && hasPlannerDebug(message)"
          class="task-chat__planner-debug"
        >
          <h4>规划检索词</h4>
          <div v-if="message.planner_metadata?.search_queries?.length" class="task-chat__planner-query-list">
            <span
              v-for="query in message.planner_metadata.search_queries"
              :key="query"
              class="task-chat__planner-query"
            >
              {{ query }}
            </span>
          </div>
          <div v-if="message.answer_debug?.confirmed_facts?.length" class="task-chat__planner-section">
            <h5>已确认事实</h5>
            <ul class="task-chat__planner-list">
              <li v-for="fact in message.answer_debug.confirmed_facts" :key="fact">{{ fact }}</li>
            </ul>
          </div>
          <div v-if="message.answer_debug?.evidence_gaps?.length" class="task-chat__planner-section">
            <h5>证据缺口</h5>
            <ul class="task-chat__planner-list">
              <li v-for="gap in message.answer_debug.evidence_gaps" :key="gap">{{ gap }}</li>
            </ul>
          </div>
        </div>

        <div v-if="message.graph_evidence?.length" class="task-chat__graph">
          <h4>认知图线索</h4>
          <template v-for="(items, groupName) in groupGraphEvidence(message.graph_evidence)" :key="groupName">
            <div v-if="items.length" class="task-chat__graph-group">
              <h5 class="task-chat__graph-group-title">
                {{
                  groupName === 'entrypoints'
                    ? '入口定位'
                    : groupName === 'callChains'
                      ? '调用链'
                      : groupName === 'symbols'
                        ? '关键符号'
                        : '关系边'
                }}
              </h5>
              <div
                v-for="(evidence, index) in items"
                :key="`${evidence.kind}-${evidence.label}-${index}`"
                class="task-chat__graph-item"
              >
                <p class="task-chat__graph-label">{{ evidence.label }}</p>
                <p v-if="evidence.path" class="task-chat__graph-path">{{ evidence.path }}</p>
                <p v-if="evidence.detail" class="task-chat__graph-detail">{{ evidence.detail }}</p>
                <div
                  v-if="evidence.kind === 'call_chain' && parseCallChain(evidence.label).length"
                  class="task-chat__chain-card"
                >
                  <h6 class="task-chat__chain-title">结构化链路</h6>
                  <div class="task-chat__chain-steps">
                    <div
                      v-for="step in parseCallChain(evidence.label)"
                      :key="step.key"
                      class="task-chat__chain-step"
                    >
                      <div
                        class="task-chat__chain-step-button"
                        :data-testid="`chain-step-${step.key}`"
                      >
                        <p class="task-chat__chain-step-title">{{ step.title }}</p>
                        <p class="task-chat__chain-step-value">{{ step.value }}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <div v-if="message.supplemental_notes.length" class="task-chat__notes">
          <h4>补充说明</h4>
          <ul>
            <li v-for="note in message.supplemental_notes" :key="note">{{ note }}</li>
          </ul>
        </div>
      </article>
    </div>

    <form class="task-chat__composer" @submit.prevent="handleSubmit">
      <label for="task-question">问题</label>
      <textarea
        id="task-question"
        v-model="question"
        name="task-question"
        rows="4"
        :disabled="!isKnowledgeReady"
        placeholder="例如：前端请求如何进入后端？哪个文件是后端入口？"
      />
      <button
        type="submit"
        data-testid="submit-task-question"
        :disabled="!canSubmit"
      >
        {{ sending ? '提问中...' : '发送问题' }}
      </button>
    </form>
  </aside>
</template>

<style scoped>
.task-chat {
  display: grid;
  gap: 16px;
  align-content: start;
}

.task-chat__header,
.task-chat__state,
.task-chat__planner-debug,
.task-chat__graph,
.task-chat__graph-group,
.task-chat__citations,
.task-chat__notes,
.task-chat__citation,
.task-chat__composer {
  display: grid;
  gap: 8px;
}

.task-chat__eyebrow,
.task-chat__header h3,
.task-chat__hint,
.task-chat__status,
.task-chat__error,
.task-chat__role,
.task-chat__content,
.task-chat__planner-debug h4,
.task-chat__planner-section h5,
.task-chat__graph h4,
.task-chat__graph-item p,
.task-chat__citation p,
.task-chat__notes h4,
.task-chat__citations h4,
.task-chat__state p,
.task-chat__state strong,
.task-chat__graph-group-title {
  margin: 0;
}

.task-chat__eyebrow {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-strong);
}

.task-chat__hint,
.task-chat__status,
.task-chat__graph-detail,
.task-chat__citation-reason {
  color: var(--muted);
}

.task-chat__state {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
}

.task-chat__state--building {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.2);
}

.task-chat__state--failed {
  background: rgba(220, 38, 38, 0.08);
  border-color: rgba(220, 38, 38, 0.2);
}

.task-chat__error {
  color: var(--danger);
  font-weight: 600;
}

.task-chat__messages {
  display: grid;
  gap: 12px;
  max-height: 520px;
  overflow: auto;
}

.task-chat__message {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.7);
}

.task-chat__message--assistant {
  background: rgba(11, 110, 79, 0.08);
}

.task-chat__message-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.task-chat__meta-badges {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.task-chat__role {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.task-chat__badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  background: rgba(15, 23, 42, 0.08);
  color: var(--text);
}

.task-chat__badge--source {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.task-chat__confidence {
  font-size: 12px;
  color: var(--muted);
}

.task-chat__graph {
  padding: 12px;
  border-radius: 14px;
  background: rgba(234, 179, 8, 0.08);
  border: 1px solid rgba(234, 179, 8, 0.18);
}

.task-chat__planner-debug {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.05);
  border: 1px solid rgba(15, 23, 42, 0.1);
}

.task-chat__planner-query-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.task-chat__planner-section {
  display: grid;
  gap: 6px;
}

.task-chat__planner-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 18px;
  color: var(--muted);
}

.task-chat__planner-query {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: rgba(15, 23, 42, 0.08);
  color: var(--text);
}

.task-chat__graph-group {
  padding-top: 8px;
  border-top: 1px solid rgba(234, 179, 8, 0.16);
}

.task-chat__graph-group:first-of-type {
  padding-top: 0;
  border-top: none;
}

.task-chat__graph-group-title {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.task-chat__graph-item {
  display: grid;
  gap: 4px;
}

.task-chat__chain-card {
  display: grid;
  gap: 8px;
  margin-top: 6px;
  padding: 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(146, 64, 14, 0.14);
}

.task-chat__chain-title,
.task-chat__chain-step-title,
.task-chat__chain-step-value {
  margin: 0;
}

.task-chat__chain-title {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
}

.task-chat__chain-steps {
  display: grid;
  gap: 8px;
}

.task-chat__chain-step {
  display: block;
}

.task-chat__chain-step-button {
  display: grid;
  width: 100%;
  gap: 2px;
  padding: 0 0 0 10px;
  border: none;
  border-left: 2px solid rgba(146, 64, 14, 0.24);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.task-chat__chain-step-button--active {
  border-left-color: #b45309;
}

.task-chat__chain-step-button:hover {
  border-left-color: #b45309;
}

.task-chat__chain-step-title {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #a16207;
}

.task-chat__chain-step-value {
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--text);
}

.task-chat__graph-label,
.task-chat__citation-path {
  font-weight: 600;
}

.task-chat__graph-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.task-chat__citation pre {
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.08);
  overflow: auto;
  white-space: pre-wrap;
}

.task-chat__citation--active {
  border-color: rgba(59, 130, 246, 0.45);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.22);
  background: rgba(59, 130, 246, 0.08);
}

.task-chat__composer textarea {
  width: 100%;
  resize: vertical;
  min-height: 120px;
  border-radius: 12px;
  border: 1px solid var(--border);
  padding: 12px;
  background: var(--panel-strong);
  color: var(--text);
  font: inherit;
}

.task-chat__composer button {
  justify-self: start;
  border: none;
  border-radius: 999px;
  padding: 10px 16px;
  background: var(--accent);
  color: #fff;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.task-chat__composer button:disabled,
.task-chat__composer textarea:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}
</style>
