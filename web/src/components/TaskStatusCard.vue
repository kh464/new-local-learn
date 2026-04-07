<script setup lang="ts">
import type { TaskStatus } from '../types/contracts'

defineProps<{
  status: TaskStatus
}>()
</script>

<template>
  <section class="panel status-card">
    <p class="status-card__label">Task {{ status.task_id }}</p>
    <h3 class="status-card__state">{{ status.state }}</h3>
    <p>Stage: {{ status.stage ?? 'waiting' }}</p>
    <p>Progress: {{ status.progress }}%</p>
    <p v-if="status.message">{{ status.message }}</p>
    <p v-else-if="status.error" class="status-card__error">{{ status.error }}</p>
  </section>
</template>

<style scoped>
.status-card {
  display: grid;
  gap: 8px;
}

.status-card__label {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-strong);
}

.status-card__state {
  margin: 0;
  text-transform: capitalize;
}

.status-card p {
  margin: 0;
}

.status-card__error {
  color: var(--danger);
}
</style>
