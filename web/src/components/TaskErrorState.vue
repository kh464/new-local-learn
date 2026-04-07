<script setup lang="ts">
defineProps<{
  title: string
  message: string
}>()
</script>

<template>
  <section class="panel error-panel">
    <h3 class="error-panel__title">{{ title }}</h3>
    <p class="error-panel__message">{{ message }}</p>
  </section>
</template>

<style scoped>
.error-panel {
  display: grid;
  gap: 8px;
}

.error-panel__title,
.error-panel__message {
  margin: 0;
}

.error-panel__message {
  color: var(--danger);
}
</style>
