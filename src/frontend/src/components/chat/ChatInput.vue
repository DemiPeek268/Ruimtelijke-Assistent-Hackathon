<script setup lang="ts">
import ButtonCallToAction from "@pzh-temporary/vue-component-library/src/components/ButtonCallToAction/ButtonCallToAction.vue";
import { computed, nextTick, ref, watch } from "vue";
import { useSuggestions } from "../../composables/useSuggestions";

const emit = defineEmits<{
	send: [text: string];
}>();

defineProps<{
	disabled?: boolean;
}>();

const { allQuestions } = useSuggestions();

const input = ref("");
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const showSuggestions = ref(false);
const selectedIndex = ref(-1);

const baseHeight = ref(0);

function autoResize() {
	if (!textareaRef.value) return;
	if (!baseHeight.value) {
		baseHeight.value = textareaRef.value.offsetHeight;
	}
	textareaRef.value.style.height = "auto";
	textareaRef.value.style.overflowY = "hidden";
	const newHeight = Math.max(textareaRef.value.scrollHeight, baseHeight.value);
	const maxHeight = parseFloat(getComputedStyle(textareaRef.value).maxHeight);
	textareaRef.value.style.height = `${newHeight}px`;
	if (newHeight >= maxHeight) {
		textareaRef.value.style.overflowY = "auto";
	}
}

watch(input, async () => {
	await nextTick();
	autoResize();
});

const filteredSuggestions = computed(() => {
	const q = input.value.trim().toLowerCase();
	if (q.length < 2) return [];
	return allQuestions.value
		.filter((s) => s.toLowerCase().includes(q))
		.slice(0, 5);
});

function handleSubmit() {
	if (!input.value.trim()) return;
	showSuggestions.value = false;
	emit("send", input.value);
	input.value = "";
}

function selectSuggestion(suggestion: string) {
	input.value = suggestion;
	showSuggestions.value = false;
	handleSubmit();
}

function handleKeydown(e: KeyboardEvent) {
	if (showSuggestions.value && filteredSuggestions.value.length > 0) {
		if (e.key === "ArrowDown") {
			e.preventDefault();
			selectedIndex.value = Math.min(
				selectedIndex.value + 1,
				filteredSuggestions.value.length - 1,
			);
			return;
		}
		if (e.key === "ArrowUp") {
			e.preventDefault();
			selectedIndex.value = Math.max(selectedIndex.value - 1, -1);
			return;
		}
		if (e.key === "Enter" && !e.shiftKey && selectedIndex.value >= 0) {
			e.preventDefault();
			const suggestion = filteredSuggestions.value[selectedIndex.value];
			if (suggestion) selectSuggestion(suggestion);
			return;
		}
		if (e.key === "Escape") {
			showSuggestions.value = false;
			return;
		}
	}

	if (e.key === "Enter" && !e.shiftKey) {
		e.preventDefault();
		handleSubmit();
	}
}

function handleInput() {
	selectedIndex.value = -1;
	showSuggestions.value = input.value.trim().length >= 2;
}

function handleBlur() {
	window.setTimeout(() => {
		showSuggestions.value = false;
	}, 150);
}
</script>

<template>
  <div class="chat-input">
    <div class="input-wrapper">
      <textarea
        ref="textareaRef"
        v-model="input"
        :disabled="disabled"
        placeholder="Stel een vraag over de ruimtelijke data..."
        rows="1"
        @keydown="handleKeydown"
        @input="handleInput"
        @blur="handleBlur"
        @focus="handleInput"
      />
      <ul v-if="showSuggestions && filteredSuggestions.length > 0" class="autocomplete">
        <li
          v-for="(s, i) in filteredSuggestions"
          :key="s"
          :class="{ selected: i === selectedIndex }"
          @mousedown.prevent="selectSuggestion(s)"
        >
          {{ s }}
        </li>
      </ul>
    </div>
    <ButtonCallToAction
      text="Verstuur"
      size="small"
      :is-disabled="disabled || !input.trim()"
      @click="handleSubmit"
    />
  </div>
</template>

<style scoped>
.chat-input {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  padding: 0.75rem;
  border-top: 1px solid #e0e0e0;
  background: white;
}

.input-wrapper {
  flex: 1;
  position: relative;
}

textarea {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  resize: none;
  font-family: inherit;
  font-size: 0.9rem;
  line-height: 1.4;
  max-height: 10rem;
  overflow-y: hidden;
}

textarea:focus {
  outline: none;
  border-color: #39870c;
  box-shadow: 0 0 0 2px rgba(57, 135, 12, 0.15);
}

.autocomplete {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin: 0 0 4px;
  padding: 0;
  list-style: none;
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);
  max-height: 200px;
  overflow-y: auto;
  z-index: 10;
}

.autocomplete li {
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
  cursor: pointer;
  color: #374151;
}

.autocomplete li:hover,
.autocomplete li.selected {
  background: #eff6ff;
  color: #2563eb;
}

.chat-input :deep(.button-call-to-action) {
  flex-shrink: 0;
  margin-bottom: 6px;
}
</style>
