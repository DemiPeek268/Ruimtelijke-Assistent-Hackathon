<script setup lang="ts">
import ButtonPrimary from "@pzh-temporary/vue-component-library/src/components/ButtonPrimary/ButtonPrimary.vue";
import ButtonSecondary from "@pzh-temporary/vue-component-library/src/components/ButtonSecondary/ButtonSecondary.vue";
import {
	COMMENT_COUNTER_THRESHOLD,
	COMMENT_MAX,
	useMessageFeedback,
} from "../../composables/useMessageFeedback";
import type { ChatMessage } from "../../types/chat";
import ThumbIcon from "./ThumbIcon.vue";

const props = defineProps<{
	message: ChatMessage;
}>();

// `commentTextareaRef` is registered inside the composable via useTemplateRef;
// the template's `ref="commentTextareaRef"` resolves through that binding, so
// we don't need (and shouldn't introduce) a local variable here.
const {
	feedbackError,
	commentSaveError,
	commentEditing,
	commentDraft,
	commentSaving,
	showCommentSection,
	savedComment,
	onFeedbackClick,
	openCommentEditor,
	cancelCommentEditor,
	saveComment,
	autoResizeComment,
} = useMessageFeedback(() => props.message);
</script>

<template>
    <div class="message-feedback">
        <div class="feedback-actions">
            <button
                type="button"
                class="feedback-btn"
                :class="{ selected: message.feedback?.rating === 'up' }"
                :aria-label="
                    message.feedback?.rating === 'up'
                        ? 'Positief beoordeeld'
                        : 'Beoordeel positief'
                "
                :aria-pressed="message.feedback?.rating === 'up'"
                @click="onFeedbackClick('up')"
            >
                <ThumbIcon direction="up" :filled="message.feedback?.rating === 'up'" />
            </button>

            <button
                type="button"
                class="feedback-btn"
                :class="{ selected: message.feedback?.rating === 'down' }"
                :aria-label="
                    message.feedback?.rating === 'down'
                        ? 'Negatief beoordeeld'
                        : 'Beoordeel negatief'
                "
                :aria-pressed="message.feedback?.rating === 'down'"
                @click="onFeedbackClick('down')"
            >
                <ThumbIcon direction="down" :filled="message.feedback?.rating === 'down'" />
            </button>

            <span
                v-if="feedbackError"
                class="feedback-error"
                role="alert"
                title="Kon feedback niet opslaan, probeer opnieuw"
                >!</span
            >
        </div>

        <div v-if="showCommentSection" class="feedback-comment">
            <div v-if="commentEditing" class="feedback-comment-editor">
                <textarea
                    ref="commentTextareaRef"
                    v-model="commentDraft"
                    class="feedback-comment-textarea"
                    placeholder="Wil je toelichten waarom? (optioneel)"
                    rows="3"
                    :maxlength="COMMENT_MAX"
                    @input="autoResizeComment"
                />
                <div class="feedback-comment-row">
                    <div class="feedback-comment-actions">
                        <ButtonSecondary
                            text="Annuleren"
                            size="small"
                            :is-disabled="commentSaving"
                            @click="cancelCommentEditor"
                        />
                        <ButtonPrimary
                            :text="commentSaving ? 'Opslaan…' : 'Opslaan'"
                            size="small"
                            :is-disabled="commentSaving"
                            @click="saveComment"
                        />
                    </div>
                    <span
                        v-if="commentDraft.length > COMMENT_COUNTER_THRESHOLD"
                        class="feedback-comment-counter"
                        :class="{ 'near-limit': commentDraft.length >= COMMENT_MAX }"
                        >{{ commentDraft.length }} / {{ COMMENT_MAX }}</span
                    >
                </div>
                <span
                    v-if="commentSaveError"
                    class="feedback-error"
                    role="alert"
                    >Kon toelichting niet opslaan, probeer opnieuw</span
                >
            </div>
            <button
                v-else
                type="button"
                class="feedback-comment-edit"
                @click="openCommentEditor"
            >
                {{ savedComment ? "Toelichting bewerken" : "+ Voeg toelichting toe" }}
            </button>
        </div>
    </div>
</template>

<style scoped>
.feedback-actions {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    margin-top: 0.35rem;
    padding: 0 0.2rem;
}

.feedback-btn {
    background: none;
    border: none;
    padding: 0.2rem;
    border-radius: 4px;
    color: #9ca3af;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
}

.feedback-btn:hover {
    color: #374151;
    background: rgba(0, 0, 0, 0.04);
}

.feedback-btn.selected {
    color: #1d4ed8;
}

.feedback-error {
    margin-left: 0.4rem;
    color: #b91c1c;
    font-weight: 700;
    cursor: help;
}

.feedback-comment {
    margin-top: 0.4rem;
    padding: 0 0.2rem;
    width: 100%;
    max-width: 22rem;
    box-sizing: border-box;
}

.feedback-comment-editor {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
}

.feedback-comment-textarea {
    width: 100%;
    padding: 0.4rem 0.55rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    resize: none;
    font-family: inherit;
    font-size: 0.8rem;
    line-height: 1.4;
    max-height: 10rem;
    overflow-y: auto;
    box-sizing: border-box;
}

.feedback-comment-textarea:focus {
    outline: none;
    border-color: #39870c;
    box-shadow: 0 0 0 2px rgba(57, 135, 12, 0.15);
}

.feedback-comment-textarea::placeholder {
    color: #9ca3af;
}

.feedback-comment-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
}

.feedback-comment-counter {
    font-size: 0.7rem;
    color: #6b7280;
}

.feedback-comment-counter.near-limit {
    color: #b91c1c;
    font-weight: 600;
}

.feedback-comment-actions {
    display: flex;
    gap: 0.4rem;
}

.feedback-comment-edit {
    background: none;
    border: none;
    padding: 0;
    font-size: 0.75rem;
    color: #6b7280;
    cursor: pointer;
    white-space: nowrap;
}

.feedback-comment-edit:hover {
    color: #374151;
    text-decoration: underline;
}
</style>
