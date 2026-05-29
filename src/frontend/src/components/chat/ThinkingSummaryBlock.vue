<script setup lang="ts">
import { ref } from "vue";
import { THINKING_STEP_LABELS } from "../../types/chat";

const props = defineProps<{
	stepId: string;
	summary?: string;
}>();

const isOpen = ref(false);

const label = THINKING_STEP_LABELS[props.stepId] ?? props.stepId;

void isOpen;
void label;
</script>

<template>
  <div class="thinking-block">
    <button class="thinking-toggle" @click="isOpen = !isOpen">
      <span class="toggle-label">{{ label }}</span>
      <span class="toggle-right">
        <svg v-if="summary === undefined" class="spinner" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="8" cy="8" r="6" stroke="#d1d5db" stroke-width="2"/>
          <path d="M8 2a6 6 0 0 1 6 6" stroke="#6b7280" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else class="checkmark" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M3 8l3.5 3.5L13 5" stroke="#9ca3af" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg class="chevron" :class="{ open: isOpen }" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </span>
    </button>
    <div v-if="isOpen" class="thinking-body">
      <span v-if="summary === undefined" class="thinking-loading">Laden…</span>
      <p v-else class="thinking-text">{{ summary }}</p>
    </div>
  </div>
</template>

<style scoped>
.thinking-block {
  margin: 0;
}

.thinking-toggle {
  display: flex;
  align-items: center;
  width: 100%;
  background: none;
  border: none;
  color: #6b7280;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  padding: 0.3rem 0.25rem;
  text-align: left;
  gap: 0.5rem;
}

.thinking-toggle:hover {
  color: #374151;
}

.toggle-label {
  flex: 1;
}

.toggle-right {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-shrink: 0;
}

.spinner {
  width: 14px;
  height: 14px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.checkmark {
  width: 14px;
  height: 14px;
}

.chevron {
  width: 14px;
  height: 14px;
  color: #9ca3af;
  transition: transform 0.2s ease;
}

.chevron.open {
  transform: rotate(90deg);
}

.thinking-body {
  margin-left: 0.25rem;
  padding-left: 0.75rem;
  border-left: 2px solid #e5e7eb;
  font-size: 0.8rem;
  color: #6b7280;
  font-style: italic;
  line-height: 1.6;
  padding-top: 0.1rem;
  padding-bottom: 0.25rem;
}

.thinking-loading {
  color: #9ca3af;
}

.thinking-text {
  margin: 0;
}
</style>
