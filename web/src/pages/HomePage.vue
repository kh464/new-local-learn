<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import RepositorySubmitForm from '../components/RepositorySubmitForm.vue'
import { createAnalysisTask } from '../services/api'

const router = useRouter()
const githubUrl = ref('')
const pending = ref(false)
const error = ref<string | null>(null)

async function handleSubmit() {
  if (pending.value || githubUrl.value.trim().length === 0) {
    return
  }

  pending.value = true
  error.value = null

  try {
    const task = await createAnalysisTask(githubUrl.value)
    await router.push(`/tasks/${task.task_id}`)
  } catch (submissionError) {
    if (submissionError instanceof Error) {
      error.value = submissionError.message
    } else {
      error.value = 'Something went wrong. Please try again.'
    }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <section class="home-hero">
    <div class="home-hero__panel">
      <p class="home-hero__eyebrow">Submit a repository to start the analysis</p>
      <h2 class="home-hero__title">Turn a GitHub project into a living tech brief.</h2>
      <p class="home-hero__subtitle">
        Paste a repo URL and the workbench will generate a structured overview of architecture, flows,
        and implementation details.
      </p>
      <RepositorySubmitForm v-model="githubUrl" :pending="pending" :error="error ?? undefined" @submit="handleSubmit" />
      <p v-if="error" class="home-hero__error" role="alert">{{ error }}</p>
    </div>
  </section>
</template>

<style scoped>
.home-hero {
  display: grid;
  place-items: center;
  padding: 24px 0 48px;
}

.home-hero__panel {
  width: min(720px, 100%);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 32px;
  box-shadow: var(--shadow);
  display: grid;
  gap: 16px;
}

.home-hero__eyebrow {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--accent-strong);
}

.home-hero__title {
  margin: 0;
  font-size: clamp(24px, 3vw, 32px);
}

.home-hero__subtitle {
  margin: 0;
  color: var(--muted);
}

.home-hero__error {
  margin: 0;
  color: var(--danger);
  font-weight: 600;
}
@media (max-width: 600px) {
  .home-hero__panel {
    padding: 24px;
  }
}
</style>
