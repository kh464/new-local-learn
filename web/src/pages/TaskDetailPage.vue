<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import AnalysisResultView from '../components/AnalysisResultView.vue'
import TaskErrorState from '../components/TaskErrorState.vue'
import TaskEventTimeline from '../components/TaskEventTimeline.vue'
import TaskStatusCard from '../components/TaskStatusCard.vue'
import { useAnalysisResult } from '../composables/useAnalysisResult'
import { useTaskStatus } from '../composables/useTaskStatus'
import { useTaskStream } from '../composables/useTaskStream'
import { cancelTask, retryTask } from '../services/api'

const props = defineProps<{
  taskId: string
}>()

const router = useRouter()
const { status, refresh, startPolling, stopPolling } = useTaskStatus(props.taskId)
const { events, connected, connect, disconnect } = useTaskStream(`/api/v1/tasks/${props.taskId}/stream`)
const { result, pending, terminalError, notFound, load } = useAnalysisResult(props.taskId)
const actionPending = ref<'cancel' | 'retry' | null>(null)

const currentStatus = computed(() => status.value)
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

async function handleCancel() {
  actionPending.value = 'cancel'
  try {
    await cancelTask(props.taskId)
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
  await refresh()
  startPolling()
  connect()
})

onBeforeUnmount(() => {
  stopPolling()
  disconnect()
})

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
      title="Task not found"
      message="The requested task does not exist or has already been removed."
    />

    <template v-else>
      <TaskStatusCard v-if="currentStatus" :status="currentStatus" />

      <section class="panel task-layout__meta">
        <p>Live stream: {{ isStreamConnected ? 'connected' : 'disconnected' }}</p>
        <p>Task ID: {{ taskId }}</p>
        <div class="task-layout__actions">
          <button
            v-if="canCancel"
            type="button"
            data-testid="cancel-task"
            :disabled="actionPending !== null"
            @click="handleCancel"
          >
            {{ actionPending === 'cancel' ? 'Cancelling...' : 'Cancel task' }}
          </button>
          <button
            v-if="canRetry"
            type="button"
            data-testid="retry-task"
            :disabled="actionPending !== null"
            @click="handleRetry"
          >
            {{ actionPending === 'retry' ? 'Retrying...' : 'Retry task' }}
          </button>
        </div>
      </section>

      <TaskEventTimeline :events="streamEvents" />

      <TaskErrorState
        v-if="isFailed && failureMessage"
        title="Task failed"
        :message="failureMessage"
      />

      <section v-else-if="resultPending" class="panel task-layout__pending">
        <h3>Result loading</h3>
        <p>The task is complete, but the final result payload is still being fetched.</p>
      </section>

      <AnalysisResultView v-else-if="currentResult" :task-id="taskId" :result="currentResult" />
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
</style>
