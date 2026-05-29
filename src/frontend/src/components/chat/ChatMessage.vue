<script setup lang="ts">
import { marked } from "marked";
import { computed } from "vue";
import type { ChatMessage } from "../../types/chat";
import { formatNumber } from "../../utils/formatting";
import MessageFeedback from "./MessageFeedback.vue";
import ThinkingSummaryBlock from "./ThinkingSummaryBlock.vue";

marked.use({ gfm: true, breaks: true });

const props = defineProps<{
	message: ChatMessage;
}>();

const renderedContent = computed(() => {
	const content = props.message.content;
	if (!content) return "";
	return marked.parse(content) as string;
});
</script>

<template>
  <div class="chat-message" :class="message.role">
    <div v-if="message.role === 'assistant' && message.thinkingSummaries?.length" class="thinking-container">
      <ThinkingSummaryBlock
        v-for="s in message.thinkingSummaries"
        :key="s.step_id"
        :step-id="s.step_id"
        :summary="s.summary"
      />
    </div>

    <div class="message-bubble">
      <div class="message-content markdown-body" v-html="renderedContent"></div>

      <div v-if="message.queryResults" class="results-info">
        {{ formatNumber(message.queryResults.length) }} resultaten gevonden
      </div>
    </div>

    <MessageFeedback
      v-if="
        message.role === 'assistant' &&
        !message.isStreaming &&
        (message.content || message.sql || message.mapPlan)
      "
      :message="message"
    />
  </div>
</template>

<style scoped>
.thinking-container {
  display: flex;
  flex-direction: column;
  max-width: 85%;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fafafa;
  padding: 0.2rem 0.5rem;
  margin-bottom: 0.4rem;
}

.chat-message {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 0.5rem 0.75rem;
}

.chat-message.user {
  align-items: flex-end;
}

.message-bubble {
  max-width: 85%;
  padding: 0.6rem 0.9rem;
  border-radius: 12px;
  font-size: 0.9rem;
  line-height: 1.5;
}

.user .message-bubble {
  background: #3b82f6;
  color: white;
  border-bottom-right-radius: 4px;
}

.user .message-content :deep(code) {
  background: rgba(255, 255, 255, 0.2);
}

.assistant .message-bubble {
  background: #f3f4f6;
  color: #1f2937;
  border-bottom-left-radius: 4px;
}

.message-content {
  word-break: break-word;
}

.message-content :deep(p) {
  margin: 0 0 0.5em 0;
}

.message-content :deep(p:last-child) {
  margin-bottom: 0;
}

.message-content :deep(strong) {
  font-weight: 600;
}

.message-content :deep(ul),
.message-content :deep(ol) {
  margin: 0.25em 0;
  padding-left: 1.5em;
}

.message-content :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.85em;
}

.message-content :deep(pre) {
  background: #1f2937;
  color: #e5e7eb;
  padding: 0.5rem;
  border-radius: 6px;
  font-size: 0.8em;
  overflow-x: auto;
  margin: 0.5em 0;
}

.message-content :deep(pre code) {
  background: none;
  padding: 0;
}

.results-info {
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: #6b7280;
}
</style>
