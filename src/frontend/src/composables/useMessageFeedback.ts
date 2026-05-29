import { computed, nextTick, ref, useTemplateRef, watch } from "vue";
import { api } from "../services/api";
import type { ChatMessage, MessageFeedback } from "../types/chat";
import { useChat } from "./useChat";

export const COMMENT_MAX = 2000;
export const COMMENT_COUNTER_THRESHOLD = 1500;

// Per-button debounce window: cross-button flips (up → down) are intentionally
// not debounced — the backend advisory lock serializes those.
const CLICK_DEBOUNCE_MS = 150;

function feedbackFromResult(result: {
	rating: "up" | "down" | null;
	comment: string | null;
	updated_at: string | null;
}): MessageFeedback | null {
	if (!result.rating || !result.updated_at) return null;
	return {
		rating: result.rating,
		comment: result.comment,
		updatedAt: result.updated_at,
	};
}

export function useMessageFeedback(message: () => ChatMessage) {
	const { sessionId, setMessageFeedback } = useChat();

	const feedbackError = ref(false);
	const commentSaveError = ref(false);
	const lastClickAt: Record<"up" | "down", number> = { up: 0, down: 0 };

	const commentEditing = ref(false);
	const commentDraft = ref("");
	const commentSaving = ref(false);
	// useTemplateRef binds by string, so vue-tsc tracks usage and the SFC can
	// keep `ref="commentTextareaRef"` without an unused-variable warning.
	const commentTextareaRef =
		useTemplateRef<HTMLTextAreaElement>("commentTextareaRef");

	const showCommentSection = computed(() => {
		const rating = message().feedback?.rating;
		return rating === "up" || rating === "down";
	});
	const savedComment = computed(() => message().feedback?.comment ?? null);

	// Drop draft state whenever the rating clears.
	watch(
		() => message().feedback?.rating,
		(rating) => {
			if (rating !== "up" && rating !== "down") {
				commentEditing.value = false;
				commentDraft.value = "";
				commentSaveError.value = false;
			}
		},
	);

	function autoResizeComment() {
		const el = commentTextareaRef.value;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${el.scrollHeight}px`;
	}

	function openCommentEditor() {
		commentDraft.value = savedComment.value ?? "";
		commentEditing.value = true;
		commentSaveError.value = false;
		nextTick(autoResizeComment);
	}

	function cancelCommentEditor() {
		commentEditing.value = false;
		commentDraft.value = "";
		commentSaveError.value = false;
	}

	async function saveComment() {
		const m = message();
		if (!sessionId.value || !m.id) return;
		const rating = m.feedback?.rating;
		if (rating !== "up" && rating !== "down") return;

		const messageId = m.id;
		const previous = m.feedback;
		const text = commentDraft.value;

		setMessageFeedback(messageId, {
			rating,
			comment: text,
			updatedAt: new Date().toISOString(),
		});
		commentSaving.value = true;
		commentSaveError.value = false;

		try {
			const result = await api.postMessageFeedback(
				sessionId.value,
				messageId,
				rating,
				text,
			);
			setMessageFeedback(messageId, feedbackFromResult(result));
			commentEditing.value = false;
		} catch {
			setMessageFeedback(messageId, previous ?? null);
			commentSaveError.value = true;
		} finally {
			commentSaving.value = false;
		}
	}

	async function onFeedbackClick(rating: "up" | "down") {
		const now = performance.now();
		if (now - lastClickAt[rating] < CLICK_DEBOUNCE_MS) return;
		lastClickAt[rating] = now;

		const m = message();
		if (!sessionId.value || !m.id) return;

		const messageId = m.id;
		const previous = m.feedback ?? null;
		const nextRating: "up" | "down" | null =
			previous?.rating === rating ? null : rating;

		setMessageFeedback(
			messageId,
			nextRating
				? { rating: nextRating, updatedAt: new Date().toISOString() }
				: null,
		);
		feedbackError.value = false;

		try {
			const result = await api.postMessageFeedback(
				sessionId.value,
				messageId,
				nextRating,
			);
			setMessageFeedback(messageId, feedbackFromResult(result));
		} catch {
			setMessageFeedback(messageId, previous);
			feedbackError.value = true;
		}
	}

	return {
		feedbackError,
		commentSaveError,
		commentEditing,
		commentDraft,
		commentSaving,
		commentTextareaRef,
		showCommentSection,
		savedComment,
		onFeedbackClick,
		openCommentEditor,
		cancelCommentEditor,
		saveComment,
		autoResizeComment,
	};
}
