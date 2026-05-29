<script setup lang="ts">
import InputSelect from "@pzh-temporary/vue-component-library/src/components/InputSelect/InputSelect.vue";
import Message from "@pzh-temporary/vue-component-library/src/components/Message/Message.vue";
import { nextTick, onMounted, ref, watch } from "vue";
import { useChat } from "../../composables/useChat";
import { useDataDictionary } from "../../composables/useDataDictionary";
import { useDuckDB } from "../../composables/useDuckDB";
import { useMap } from "../../composables/useMap";
import { useSessions } from "../../composables/useSessions";
import ChatInput from "./ChatInput.vue";
import ChatMessage from "./ChatMessage.vue";
import SuggestionChips from "./SuggestionChips.vue";

const {
	messages,
	isStreaming,
	sendMessage,
	model,
	clearMessages,
	loadSession,
} = useChat();
const { isReady: dbReady, isLoading: dbLoading } = useDuckDB();
const { isLoading: dictionaryLoading, error: dictionaryError } =
	useDataDictionary();
const { clearHexagons } = useMap();
const {
	sessions,
	isLoading: isLoadingSessions,
	fetchSessions,
	deleteSession,
} = useSessions();

const showHistory = ref(false);

const modelOptions = [
	{ value: "gpt-5-chat", text: "GPT-5" },
	{ value: "gpt-5.2-chat", text: "GPT-5.2" },
	{ value: "o4-mini", text: "o4-mini" },
	{ value: "Mistral-Large-3", text: "Mistral Large 3" },
];

onMounted(() => {
	fetchSessions();
});

function startNewChat() {
	clearMessages();
	clearHexagons();
	showHistory.value = false;
	fetchSessions();
}

function toggleHistory() {
	showHistory.value = !showHistory.value;
	if (showHistory.value) {
		fetchSessions();
	}
}

function handleSelectSession(id: string) {
	showHistory.value = false;
	handleLoadSession(id);
}

function handleDeleteSession(id: string) {
	deleteSession(id);
	if (sessions.value.length === 0) {
		showHistory.value = false;
	}
}

async function handleLoadSession(id: string) {
	clearHexagons();
	await loadSession(id);
}

const messagesContainer = ref<HTMLElement | null>(null);

function handleSend(text: string) {
	sendMessage(text);
}

// Auto-scroll on new messages
watch(
	() => messages.value.length,
	async () => {
		await nextTick();
		if (messagesContainer.value) {
			messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
		}
	},
);

// Also scroll during streaming
watch(
	() => messages.value[messages.value.length - 1]?.content,
	async () => {
		await nextTick();
		if (messagesContainer.value) {
			messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
		}
	},
);
</script>

<template>
  <div class="chat-panel">
    <div class="chat-toolbar">
      <button class="toolbar-icon-btn" title="Nieuw gesprek" @click="startNewChat">
        <svg width="18" height="18" viewBox="0 0 512 512" fill="currentColor">
          <path d="M0 64C0 28.7 28.7 0 64 0H448c35.3 0 64 28.7 64 64V352c0 35.3-28.7 64-64 64H309.3L185.6 508.8c-4.8 3.6-11.3 4.2-16.8 1.5s-8.8-8.2-8.8-14.3V416H64c-35.3 0-64-28.7-64-64V64zM232 296c0 13.3 10.7 24 24 24s24-10.7 24-24V232h64c13.3 0 24-10.7 24-24s-10.7-24-24-24H280V120c0-13.3-10.7-24-24-24s-24 10.7-24 24v64H168c-13.3 0-24 10.7-24 24s10.7 24 24 24h64v64z"/>
        </svg>
      </button>
      <button class="toolbar-icon-btn" :class="{ active: showHistory }" title="Geschiedenis" @click="toggleHistory">
        <svg width="18" height="18" viewBox="0 0 512 512" fill="currentColor">
          <path d="M75 75L41 41C25.9 25.9 0 36.6 0 57.9V168c0 13.3 10.7 24 24 24H134.1c21.4 0 32.1-25.9 17-41l-30.8-30.8C155 85.5 203 64 256 64c106 0 192 86 192 192s-86 192-192 192c-40.8 0-78.6-12.7-109.7-34.4c-14.5-10.1-34.4-6.6-44.6 7.9s-6.6 34.4 7.9 44.6C151.2 495 201.7 512 256 512c141.4 0 256-114.6 256-256S397.4 0 256 0C185.3 0 121.3 28.7 75 75zm181 53c-13.3 0-24 10.7-24 24V256c0 6.4 2.5 12.5 7 17l72 72c9.4 9.4 24.6 9.4 33.9 0s9.4-24.6 0-33.9l-65-65V152c0-13.3-10.7-24-24-24z"/>
        </svg>
      </button>
      <div class="toolbar-divider" />
      <InputSelect
        v-model="model"
        :options="modelOptions"
        :placeholder="null"
        size="small"
        class="model-select"
      />
    </div>

    <div v-if="showHistory" class="session-history">
      <h3 class="session-history-title">Eerdere gesprekken</h3>
      <div v-if="isLoadingSessions" class="session-history-empty">
        Laden...
      </div>
      <div v-else-if="sessions.length === 0" class="session-history-empty">
        Geen eerdere gesprekken.
      </div>
      <div
        v-for="s in sessions"
        v-else
        :key="s.id"
        class="session-item"
        @click="handleSelectSession(s.id)"
      >
        <span class="session-item-title">{{ s.title || 'Naamloos gesprek' }}</span>
        <span class="session-item-date">{{ new Date(s.updated_at).toLocaleDateString('nl-NL') }}</span>
        <button
          class="session-delete-btn"
          title="Verwijderen"
          @click.stop="handleDeleteSession(s.id)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>

    <div ref="messagesContainer" class="messages">
      <div v-if="dictionaryError" class="dictionary-error">
        <Message
          type="warning"
          title="Geen toegang"
          :message="dictionaryError"
        />
      </div>
      <template v-else>
        <div v-if="dbLoading" class="status-message">
          Database laden...
        </div>
        <div v-else-if="dictionaryLoading" class="status-message">
          Data-bibliotheek laden...
        </div>
        <Message
          v-else-if="!dbReady"
          type="error"
          message="Database kon niet geladen worden."
        />

        <SuggestionChips
          v-if="messages.length === 0 && dbReady && !dictionaryLoading"
          @select="handleSend"
        />

        <ChatMessage
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
        />
      </template>
    </div>

    <ChatInput
      :disabled="isStreaming || !dbReady || dictionaryLoading || !!dictionaryError"
      @send="handleSend"
    />
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
}

.chat-toolbar {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid #e5e7eb;
}

.toolbar-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #4b5563;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.toolbar-icon-btn:hover {
  background: #f3f4f6;
  color: #1f2937;
}

.toolbar-icon-btn.active {
  background: #e5e7eb;
  color: #1f2937;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: #e5e7eb;
  margin: 0 0.25rem;
}

.model-select {
  margin-left: auto;
}

.model-select :deep(.pzh-input-select__input-wrapper) {
  min-width: 140px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 0;
}

.status-message {
  text-align: center;
  padding: 2rem 1rem;
  color: #6b7280;
  font-size: 0.9rem;
}

.dictionary-error {
  margin: 1rem;
}

.session-history {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #e5e7eb;
  max-height: 50%;
  overflow-y: auto;
}

.session-history-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.session-history-empty {
  color: #9ca3af;
  font-size: 0.875rem;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
}

.session-item:hover {
  background: #f3f4f6;
}

.session-item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1f2937;
}

.session-item-date {
  color: #9ca3af;
  font-size: 0.75rem;
  white-space: nowrap;
}

.session-delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}

.session-item:hover .session-delete-btn {
  opacity: 1;
}

.session-delete-btn:hover {
  color: #ef4444;
  background: #fef2f2;
}
</style>
