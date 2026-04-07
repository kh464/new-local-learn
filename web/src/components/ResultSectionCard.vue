<script setup lang="ts">
defineProps<{
  title: string
  eyebrow?: string
}>()
</script>

<template>
  <section class="panel result-card">
    <header class="result-card__header">
      <p v-if="eyebrow" class="result-card__eyebrow">{{ eyebrow }}</p>
      <h3 class="result-card__title">{{ title }}</h3>
    </header>
    <div class="result-card__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.result-card {
  display: grid;
  gap: 12px;
}

.result-card__header {
  display: grid;
  gap: 4px;
}

.result-card__eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}

.result-card__title {
  margin: 0;
}

.result-card__body :deep(p),
.result-card__body :deep(ul),
.result-card__body :deep(pre) {
  margin: 0;
}

.result-card__body :deep(ul) {
  padding-left: 20px;
  display: grid;
  gap: 6px;
}
</style>
