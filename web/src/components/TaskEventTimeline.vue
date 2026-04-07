<script setup lang="ts">
import type { TaskStreamEvent } from '../types/contracts'

defineProps<{
  events: TaskStreamEvent[]
}>()
</script>

<template>
  <section class="panel timeline">
    <h3 class="timeline__title">Task Timeline</h3>
    <ol class="timeline__list">
      <li v-for="(event, index) in events" :key="`${event.stage ?? 'event'}-${index}`" class="timeline__item">
        <strong>{{ event.stage ?? 'update' }}</strong>
        <span v-if="event.progress !== undefined"> {{ event.progress }}%</span>
        <span v-if="event.message"> - {{ event.message }}</span>
        <span v-if="event.error"> - {{ event.error }}</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.timeline {
  display: grid;
  gap: 12px;
}

.timeline__title {
  margin: 0;
}

.timeline__list {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 8px;
}
</style>
