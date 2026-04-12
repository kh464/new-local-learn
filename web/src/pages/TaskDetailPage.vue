<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import AnalysisResultView from '../components/AnalysisResultView.vue'
import CodeGraphPanel from '../components/CodeGraphPanel.vue'
import TaskChatPanel from '../components/TaskChatPanel.vue'
import TaskErrorState from '../components/TaskErrorState.vue'
import TaskEventTimeline from '../components/TaskEventTimeline.vue'
import TaskStatusCard from '../components/TaskStatusCard.vue'
import { useAnalysisResult } from '../composables/useAnalysisResult'
import { useTaskStatus } from '../composables/useTaskStatus'
import { useTaskStream } from '../composables/useTaskStream'
import { retryTask, stopTask } from '../services/api'

const props = defineProps<{
  taskId: string
}>()

const router = useRouter()
const { status, loadError, refresh, startPolling, stopPolling } = useTaskStatus(props.taskId)
const { events, connected, connect, disconnect } = useTaskStream(`/api/v1/tasks/${props.taskId}/stream`)
const { result, pending, terminalError, notFound, load } = useAnalysisResult(props.taskId)

const actionPending = ref<'stop' | 'retry' | null>(null)
const highlightedNodeIds = ref<string[]>([])
const selectedNodeIds = ref<string[]>([])

const currentStatus = computed(() => status.value)
const statusLoadError = computed(() => loadError.value)
const streamEvents = computed(() => events.value)
const isStreamConnected = computed(() => connected.value)
const currentResult = computed(() => result.value)
const resultPending = computed(() => pending.value)
const isNotFound = computed(() => notFound.value)

const isSucceeded = computed(() => currentStatus.value?.state === 'succeeded')
const canCancel = computed(() => {
  const state = currentStatus.value?.state
  return state === 'queued' || state === 'running'
})
const canRetry = computed(() => {
  const state = currentStatus.value?.state
  return state === 'failed' || state === 'cancelled'
})
const isFailed = computed(() => {
  const state = currentStatus.value?.state
  return state === 'failed' || state === 'cancelled'
})
const failureMessage = computed(() => currentStatus.value?.error ?? terminalError.value)
const showChatPanel = computed(() => isSucceeded.value && Boolean(currentResult.value))

async function handleStop() {
  actionPending.value = 'stop'
  try {
    await stopTask(props.taskId)
    await refresh()
  } finally {
    actionPending.value = null
  }
}

async function handleRetry() {
  actionPending.value = 'retry'
  try {
    const nextTask = await retryTask(props.taskId)
    await router.push(`/tasks/${nextTask.task_id}`)
  } finally {
    actionPending.value = null
  }
}

onMounted(async () => {
  await refresh().catch(() => undefined)
  startPolling()
  connect()
})

onBeforeUnmount(() => {
  stopPolling()
  disconnect()
})

watch(
  () => props.taskId,
  () => {
    highlightedNodeIds.value = []
    selectedNodeIds.value = []
  },
  { immediate: true },
)

watch(
  isSucceeded,
  async (value) => {
    if (value) {
      await load()
      stopPolling()
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="task-layout">
    <TaskErrorState
      v-if="isNotFound"
      title="查无此任务"
      message="请求的任务不存在，或者已经被移除。"
    />

    <template v-else>
      <TaskStatusCard v-if="currentStatus" :status="currentStatus" />

      <TaskErrorState
        v-if="!currentStatus && statusLoadError"
        title="任务状态加载失败"
        :message="statusLoadError"
      />

      <section class="panel task-layout__meta">
        <p>实时流：{{ isStreamConnected ? '已连接' : '已断开' }}</p>
        <p>任务编号：{{ taskId }}</p>
        <div class="task-layout__actions">
          <button
            v-if="canCancel"
            type="button"
            data-testid="stop-task"
            :disabled="actionPending !== null"
            @click="handleStop"
          >
            {{ actionPending === 'stop' ? '正在停止...' : '停止分析' }}
          </button>
          <button
            v-if="canRetry"
            type="button"
            data-testid="retry-task"
            :disabled="actionPending !== null"
            @click="handleRetry"
          >
            {{ actionPending === 'retry' ? '正在重试...' : '重试任务' }}
          </button>
        </div>
      </section>

      <TaskEventTimeline
        v-if="currentStatus || !statusLoadError"
        :status="currentStatus ?? null"
        :events="streamEvents"
      />

      <TaskErrorState
        v-if="isFailed && failureMessage"
        title="任务失败"
        :message="failureMessage"
      />

      <section v-else-if="resultPending" class="panel task-layout__pending">
        <h3>结果加载中</h3>
        <p>任务已经完成，正在获取最终分析结果。</p>
      </section>

      <section v-else-if="currentResult" class="task-layout__workspace">
        <AnalysisResultView :task-id="taskId" :result="currentResult" />
        <div class="task-layout__sidecar">
          <CodeGraphPanel
            v-if="showChatPanel"
            :task-id="taskId"
            :highlighted-node-ids="highlightedNodeIds"
            @select-node="selectedNodeIds = $event"
          />
          <TaskChatPanel
            v-if="showChatPanel"
            :task-id="taskId"
            :status="currentStatus ?? null"
            :selected-node-ids="selectedNodeIds"
            @highlight-related-nodes="highlightedNodeIds = $event"
          />
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.task-layout {
  display: grid;
  gap: 20px;
}

.task-layout__meta,
.task-layout__pending {
  display: grid;
  gap: 8px;
}

.task-layout__workspace {
  display: grid;
  gap: 20px;
  align-items: start;
}

.task-layout__sidecar {
  display: grid;
  gap: 20px;
  align-content: start;
}

.task-layout__actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.task-layout__actions button {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text);
  padding: 10px 14px;
  font: inherit;
  cursor: pointer;
}

.task-layout__actions button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.task-layout__meta p,
.task-layout__pending h3,
.task-layout__pending p {
  margin: 0;
}

@media (min-width: 1200px) {
  .task-layout__workspace {
    grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
  }
}
</style>
