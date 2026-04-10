<script setup lang="ts">
import { computed } from 'vue'

const model = defineModel<string>({ default: '' })

const props = defineProps<{
  pending: boolean
}>()

const emit = defineEmits<{
  (event: 'submit'): void
}>()

const isDisabled = computed(() => props.pending || model.value.trim().length === 0)

function onSubmit() {
  if (isDisabled.value) {
    return
  }

  emit('submit')
}
</script>

<template>
  <form class="repo-submit" @submit.prevent="onSubmit">
    <label class="repo-submit__label" for="github-url">GitHub 仓库地址</label>
    <input
      id="github-url"
      v-model="model"
      class="repo-submit__input"
      type="url"
      name="github-url"
      autocomplete="off"
      placeholder="https://github.com/octocat/Hello-World"
    />
    <button class="repo-submit__button" type="submit" :disabled="isDisabled">
      {{ props.pending ? '提交中...' : '开始分析' }}
    </button>
  </form>
</template>

<style scoped>
.repo-submit {
  display: grid;
  gap: 12px;
}

.repo-submit__label {
  font-size: 14px;
  color: var(--muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.repo-submit__input {
  width: 100%;
  border-radius: 12px;
  border: 1px solid var(--border);
  padding: 12px 14px;
  font-size: 16px;
  background: var(--panel-strong);
  color: var(--text);
}

.repo-submit__input:focus {
  outline: 2px solid rgba(11, 110, 79, 0.25);
  outline-offset: 2px;
}

.repo-submit__button {
  align-self: start;
  border: none;
  border-radius: 999px;
  padding: 12px 20px;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  background: var(--accent);
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease;
}

.repo-submit__button:disabled {
  cursor: not-allowed;
  background: rgba(11, 110, 79, 0.5);
  transform: none;
}
</style>
