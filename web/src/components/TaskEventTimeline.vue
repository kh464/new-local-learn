<script setup lang="ts">
import { computed } from 'vue'

import { formatTaskStageZh, orderedTaskStages } from '../presentation/copy'
import type { TaskStage, TaskStatus, TaskStreamEvent } from '../types/contracts'

type StageState = 'completed' | 'current' | 'failed' | 'upcoming'

const props = defineProps<{
  status: TaskStatus | null
  events: TaskStreamEvent[]
}>()

const currentStageIndex = computed(() => {
  const stage = props.status?.stage
  return stage ? orderedTaskStages.indexOf(stage) : -1
})

const latestDetail = computed(() => {
  const latestEventWithDetail = [...props.events].reverse().find((event) => event.error || event.message)
  return latestEventWithDetail?.error ?? latestEventWithDetail?.message ?? props.status?.error ?? props.status?.message ?? ''
})

const stageItems = computed(() =>
  orderedTaskStages.map((stage, index) => ({
    stage,
    label: formatTaskStageZh(stage),
    state: resolveStageState(stage, index, props.status, currentStageIndex.value),
  })),
)

const activeStageLabel = computed(() => {
  if (!props.status?.stage) {
    return '等待开始'
  }

  return formatTaskStageZh(props.status.stage)
})

function resolveStageState(
  stage: TaskStage,
  index: number,
  status: TaskStatus | null,
  activeIndex: number,
): StageState {
  if (!status) {
    return 'upcoming'
  }

  if (status.state === 'succeeded') {
    return 'completed'
  }

  if (status.state === 'failed' || status.state === 'cancelled') {
    if (stage === status.stage) {
      return 'failed'
    }
    return activeIndex >= 0 && index < activeIndex ? 'completed' : 'upcoming'
  }

  if (activeIndex >= 0 && index < activeIndex) {
    return 'completed'
  }

  if (stage === status.stage) {
    return 'current'
  }

  return 'upcoming'
}

function stageStatusText(state: StageState): string {
  switch (state) {
    case 'completed':
      return '已完成'
    case 'current':
      return '进行中'
    case 'failed':
      return '失败'
    default:
      return '未开始'
  }
}
</script>

<template>
  <section class="panel timeline">
    <div class="timeline__header">
      <div>
        <h3 class="timeline__title">任务时间线</h3>
        <p class="timeline__summary">当前阶段：{{ activeStageLabel }}</p>
      </div>
      <strong class="timeline__progress">{{ status?.progress ?? 0 }}%</strong>
    </div>

    <div class="timeline__bar" aria-hidden="true">
      <span class="timeline__bar-fill" :style="{ width: `${status?.progress ?? 0}%` }" />
    </div>

    <ol class="timeline__list">
      <li
        v-for="item in stageItems"
        :key="item.stage"
        class="timeline__item"
        :data-state="item.state"
      >
        <span class="timeline__marker">{{ item.state === 'completed' ? '✓' : item.state === 'failed' ? '!' : '' }}</span>
        <div class="timeline__content">
          <strong>{{ item.label }}</strong>
          <span>{{ stageStatusText(item.state) }}</span>
        </div>
      </li>
    </ol>

    <p v-if="latestDetail" class="timeline__detail">{{ latestDetail }}</p>
  </section>
</template>

<style scoped>
.timeline {
  display: grid;
  gap: 16px;
}

.timeline__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.timeline__title,
.timeline__summary,
.timeline__detail {
  margin: 0;
}

.timeline__summary {
  color: var(--muted);
}

.timeline__progress {
  font-size: 24px;
  line-height: 1;
}

.timeline__bar {
  width: 100%;
  height: 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.timeline__bar-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-strong));
  border-radius: inherit;
  transition: width 180ms ease;
}

.timeline__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}

.timeline__item {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.timeline__item[data-state='current'] {
  border-color: rgba(20, 184, 166, 0.4);
  background: rgba(20, 184, 166, 0.08);
}

.timeline__item[data-state='completed'] {
  border-color: rgba(59, 130, 246, 0.18);
}

.timeline__item[data-state='failed'] {
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(220, 38, 38, 0.08);
}

.timeline__marker {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.08);
  font-weight: 700;
}

.timeline__item[data-state='current'] .timeline__marker {
  background: var(--accent);
  color: white;
}

.timeline__item[data-state='completed'] .timeline__marker {
  background: rgba(59, 130, 246, 0.14);
  color: #1d4ed8;
}

.timeline__item[data-state='failed'] .timeline__marker {
  background: rgba(220, 38, 38, 0.18);
  color: #b91c1c;
}

.timeline__content {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.timeline__content span {
  color: var(--muted);
}

.timeline__detail {
  color: var(--danger);
  word-break: break-word;
}
</style>
