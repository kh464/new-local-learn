<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { AuditEventQuery, AuditEventsPage, MetricsSnapshot, TaskListPage, TaskState } from '../types/contracts'
import { fetchAuditEvents, fetchMetricsSnapshot, fetchTaskList } from '../services/api'

const defaultAuditPageSize = 25
const defaultTaskPageSize = 8
const auditPage = ref<AuditEventsPage>({
  events: [],
  total: 0,
  limit: defaultAuditPageSize,
  offset: 0,
})
const taskPage = ref<TaskListPage>({
  tasks: [],
  total: 0,
  limit: defaultTaskPageSize,
  offset: 0,
})
const metrics = ref<MetricsSnapshot>({})
const loading = ref(false)
const error = ref<string | null>(null)
const taskStateFilter = ref<TaskState | ''>('')
const auditFilters = ref<AuditEventQuery>({
  action: '',
  outcome: '',
  task_id: '',
  request_id: '',
  subject: '',
})

const metricEntries = computed(() =>
  Object.entries(metrics.value).sort(([left], [right]) => left.localeCompare(right)),
)
const hasPreviousAuditPage = computed(() => auditPage.value.offset > 0)
const hasNextAuditPage = computed(
  () => auditPage.value.offset + auditPage.value.events.length < auditPage.value.total,
)
const taskPanelSummary = computed(() => `${taskPage.value.tasks.length} of ${taskPage.value.total} tasks`)
const auditPageSummary = computed(() => {
  if (auditPage.value.total === 0) {
    return 'No events'
  }

  const start = auditPage.value.offset + 1
  const end = auditPage.value.offset + auditPage.value.events.length
  return `${start}-${end} of ${auditPage.value.total}`
})

function buildAuditQuery(offset = 0): AuditEventQuery {
  const query: AuditEventQuery = {
    limit: defaultAuditPageSize,
    offset,
  }

  const optionalEntries: Array<[keyof AuditEventQuery, string | undefined]> = [
    ['action', auditFilters.value.action?.trim()],
    ['outcome', auditFilters.value.outcome?.trim()],
    ['task_id', auditFilters.value.task_id?.trim()],
    ['request_id', auditFilters.value.request_id?.trim()],
    ['subject', auditFilters.value.subject?.trim()],
  ]

  for (const [key, value] of optionalEntries) {
    if (value) {
      query[key] = value
    }
  }

  return query
}

async function loadAuditEvents(offset = 0) {
  auditPage.value = await fetchAuditEvents(buildAuditQuery(offset))
}

async function loadTasks() {
  taskPage.value = await fetchTaskList({
    limit: defaultTaskPageSize,
    offset: 0,
    state: taskStateFilter.value || undefined,
  })
}

async function load() {
  loading.value = true
  error.value = null

  try {
    const [eventsPayload, metricsPayload, tasksPayload] = await Promise.all([
      fetchAuditEvents(buildAuditQuery()),
      fetchMetricsSnapshot(),
      fetchTaskList({
        limit: defaultTaskPageSize,
        offset: 0,
        state: taskStateFilter.value || undefined,
      }),
    ])
    auditPage.value = eventsPayload
    metrics.value = metricsPayload
    taskPage.value = tasksPayload
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Failed to load admin data.'
  } finally {
    loading.value = false
  }
}

async function applyAuditFilters() {
  loading.value = true
  error.value = null

  try {
    await loadAuditEvents(0)
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Failed to load audit events.'
  } finally {
    loading.value = false
  }
}

async function applyTaskFilter() {
  loading.value = true
  error.value = null

  try {
    await loadTasks()
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Failed to load tasks.'
  } finally {
    loading.value = false
  }
}

async function goToPreviousAuditPage() {
  if (!hasPreviousAuditPage.value) {
    return
  }

  loading.value = true
  error.value = null

  try {
    await loadAuditEvents(Math.max(auditPage.value.offset - auditPage.value.limit, 0))
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Failed to load audit events.'
  } finally {
    loading.value = false
  }
}

async function goToNextAuditPage() {
  if (!hasNextAuditPage.value) {
    return
  }

  loading.value = true
  error.value = null

  try {
    await loadAuditEvents(auditPage.value.offset + auditPage.value.limit)
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Failed to load audit events.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="admin-layout">
    <header class="panel admin-hero">
      <p class="admin-hero__eyebrow">Operations</p>
      <h2>Operations Console</h2>
      <p>
        Monitor recent audit activity and backend counters without leaving the workbench.
      </p>
    </header>

    <p v-if="loading" class="admin-status">Loading admin data...</p>
    <p v-else-if="error" class="admin-status admin-status--error" role="alert">{{ error }}</p>

    <div v-else class="admin-grid">
      <section class="panel admin-panel">
        <div class="admin-panel__header">
          <h3>Metrics Snapshot</h3>
          <span>{{ metricEntries.length }} metrics</span>
        </div>
        <dl class="metric-list">
          <div v-for="[name, value] in metricEntries" :key="name" class="metric-list__item">
            <dt>{{ name }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
      </section>

      <section class="panel admin-panel">
        <div class="admin-panel__header">
          <h3>Recent Tasks</h3>
          <span>{{ taskPanelSummary }}</span>
        </div>
        <div class="task-toolbar">
          <label>
            State
            <select v-model="taskStateFilter" name="task-state">
              <option value="">All</option>
              <option value="queued">queued</option>
              <option value="running">running</option>
              <option value="succeeded">succeeded</option>
              <option value="failed">failed</option>
              <option value="cancelled">cancelled</option>
            </select>
          </label>
          <button type="button" data-testid="task-filter-submit" @click="applyTaskFilter">Refresh tasks</button>
        </div>
        <ul class="task-list">
          <li v-for="task in taskPage.tasks" :key="task.task_id" class="task-list__item">
            <div class="task-list__main">
              <p class="task-list__title">
                <strong>{{ task.task_id }}</strong>
                <span>{{ task.state }}</span>
              </p>
              <p class="task-list__meta">
                {{ task.github_url ?? 'No repository URL recorded' }}
              </p>
              <p class="task-list__meta">
                Progress {{ task.progress }}%<span v-if="task.stage"> · {{ task.stage }}</span>
              </p>
            </div>
            <a class="task-list__link" :href="`/tasks/${task.task_id}`">Open task</a>
          </li>
        </ul>
        <p v-if="!taskPage.tasks.length" class="task-list__empty">No tasks matched the current filter.</p>
      </section>

      <section class="panel admin-panel">
        <div class="admin-panel__header">
          <h3>Recent Audit Events</h3>
          <span>{{ auditPageSummary }}</span>
        </div>
        <form class="audit-filters" @submit.prevent="applyAuditFilters">
          <label>
            Action
            <input v-model="auditFilters.action" name="action" type="text" placeholder="task_artifact_download" />
          </label>
          <label>
            Outcome
            <select v-model="auditFilters.outcome" name="outcome">
              <option value="">All</option>
              <option value="accepted">accepted</option>
              <option value="success">success</option>
              <option value="denied">denied</option>
            </select>
          </label>
          <label>
            Task ID
            <input v-model="auditFilters.task_id" name="task_id" type="text" placeholder="task-123" />
          </label>
          <label>
            Subject
            <input v-model="auditFilters.subject" name="subject" type="text" placeholder="worker" />
          </label>
          <button type="submit">Apply filters</button>
        </form>
        <ul class="audit-list">
          <li
            v-for="event in auditPage.events"
            :key="`${event.request_id ?? 'no-request'}-${event.task_id ?? 'no-task'}-${event.action}`"
            class="audit-list__item"
          >
            <p class="audit-list__title">
              <strong>{{ event.action }}</strong>
              <span>{{ event.outcome }}</span>
            </p>
            <p class="audit-list__meta">
              {{ event.method ?? 'N/A' }} {{ event.path ?? '' }}
            </p>
            <p v-if="event.request_id" class="audit-list__meta">Request: {{ event.request_id }}</p>
            <p v-if="event.task_id" class="audit-list__meta">Task: {{ event.task_id }}</p>
            <p v-if="event.subject" class="audit-list__meta">Subject: {{ event.subject }}</p>
          </li>
        </ul>
        <p v-if="!auditPage.events.length" class="audit-list__empty">No audit events matched the current filters.</p>
        <div class="audit-pagination">
          <button
            type="button"
            data-testid="audit-prev-page"
            :disabled="!hasPreviousAuditPage || loading"
            @click="goToPreviousAuditPage"
          >
            Previous
          </button>
          <span>{{ auditPageSummary }}</span>
          <button
            type="button"
            data-testid="audit-next-page"
            :disabled="!hasNextAuditPage || loading"
            @click="goToNextAuditPage"
          >
            Next
          </button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.admin-layout {
  display: grid;
  gap: 20px;
}

.admin-hero {
  display: grid;
  gap: 10px;
}

.admin-hero h2,
.admin-hero p {
  margin: 0;
}

.admin-hero__eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent-strong);
}

.admin-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}

.admin-panel {
  display: grid;
  gap: 16px;
}

.audit-filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.audit-filters label {
  display: grid;
  gap: 6px;
  font-size: 14px;
  color: var(--muted);
}

.audit-filters input,
.audit-filters select,
.audit-filters button,
.audit-pagination button {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text);
  padding: 10px 12px;
  font: inherit;
}

.audit-filters button,
.audit-pagination button {
  cursor: pointer;
}

.audit-filters button {
  align-self: end;
}

.admin-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 16px;
}

.admin-panel__header h3,
.admin-panel__header span {
  margin: 0;
}

.metric-list {
  display: grid;
  gap: 12px;
  margin: 0;
}

.metric-list__item {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.metric-list__item dt,
.metric-list__item dd {
  margin: 0;
}

.metric-list__item dd {
  font-weight: 700;
}

.task-toolbar {
  display: flex;
  align-items: end;
  gap: 12px;
}

.task-toolbar label {
  display: grid;
  gap: 6px;
  font-size: 14px;
  color: var(--muted);
  flex: 1;
}

.task-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 12px;
}

.task-list__item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.task-list__main {
  display: grid;
  gap: 6px;
}

.task-list__title,
.task-list__meta {
  margin: 0;
}

.task-list__title {
  display: flex;
  gap: 12px;
  align-items: center;
}

.task-list__meta,
.task-list__empty {
  color: var(--muted);
  font-size: 14px;
}

.task-list__link {
  color: var(--accent-strong);
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
}

.audit-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 12px;
}

.audit-list__item {
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.audit-list__title,
.audit-list__meta,
.admin-status {
  margin: 0;
}

.audit-list__title {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.audit-list__meta {
  color: var(--muted);
  font-size: 14px;
}

.audit-list__empty {
  margin: 0;
  color: var(--muted);
}

.audit-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.audit-pagination span {
  color: var(--muted);
  font-size: 14px;
}

.audit-pagination button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.admin-status--error {
  color: var(--danger);
  font-weight: 600;
}

@media (max-width: 900px) {
  .admin-grid {
    grid-template-columns: 1fr;
  }

  .audit-filters {
    grid-template-columns: 1fr;
  }
}
</style>
