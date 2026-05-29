import { ref } from "vue";
import { api } from "../services/api";
import { streamSSE } from "../services/sseClient";
import type {
	ChatMessage,
	MapPlan,
	MessageFeedback,
	SSEEventType,
} from "../types/chat";
import { THINKING_STEP_LABELS } from "../types/chat";
import { generateId } from "../utils/formatting";
import { useDuckDB } from "./useDuckDB";
import { useMap } from "./useMap";

const messages = ref<ChatMessage[]>([]);
const isStreaming = ref(false);
const model = ref("gpt-5-chat");
const sessionId = ref<string | null>(null);

export function useChat() {
	const { executeQuery } = useDuckDB();
	const { updateHexagons } = useMap();

	let abortController: AbortController | null = null;

	async function sendMessage(text: string) {
		if (!text.trim() || isStreaming.value) return;

		const userMsg: ChatMessage = {
			id: generateId(),
			role: "user",
			content: text.trim(),
		};
		messages.value.push(userMsg);

		const assistantMsg: ChatMessage = {
			id: generateId(),
			role: "assistant",
			content: "",
			isStreaming: true,
		};
		messages.value.push(assistantMsg);

		isStreaming.value = true;
		abortController = new AbortController();

		const history = messages.value
			.filter((m) => !m.isStreaming)
			.map((m) => ({ role: m.role, content: m.content }));

		const requestBody = {
			messages: history,
			model: model.value,
			session_id: sessionId.value,
		};

		const pendingSql: string | null = null;
		let pendingMapPlan: MapPlan | null = null;
		let pendingMapData: Record<string, unknown>[] | null = null;

		try {
			await streamSSE(
				api.getChatUrl(),
				requestBody,
				async (event: SSEEventType, data: string) => {
					const msgIdx = messages.value.length - 1;
					const msg = messages.value[msgIdx];
					if (!msg) return;

					switch (event) {
						case "meta": {
							const parsed = JSON.parse(data);
							if (parsed.session_id) {
								sessionId.value = parsed.session_id;
							}
							// Swap the client-side temp id for the server-issued message id
							// so feedback and other downstream features can address the
							// assistant turn from the first chunk onward.
							// TODO: frontend test — no frontend test infra yet (see plan).
							if (parsed.message_id) {
								msg.id = parsed.message_id;
							}
							break;
						}
						case "text": {
							const parsed = JSON.parse(data);
							msg.content += parsed.content ?? "";
							break;
						}
						case "map_config": {
							pendingMapPlan = JSON.parse(data);
							msg.mapPlan = pendingMapPlan!;
							break;
						}
						case "map_data": {
							const parsed = JSON.parse(data);
							pendingMapData = parsed.rows;
							break;
						}
						case "status": {
							const parsed = JSON.parse(data);
							if (
								parsed.status === "active" &&
								parsed.step in THINKING_STEP_LABELS
							) {
								msg.thinkingSummaries ??= [];
								msg.thinkingSummaries.push({ step_id: parsed.step });
							}
							break;
						}
						case "step_thinking_summary": {
							const parsed = JSON.parse(data);
							msg.thinkingSummaries ??= [];
							const matches = msg.thinkingSummaries.filter(
								(s) => s.step_id === parsed.step_id,
							);
							const entry = matches[matches.length - 1];
							if (entry) {
								entry.summary = parsed.summary;
							}
							break;
						}
						case "error": {
							const parsed = JSON.parse(data);
							msg.content += `\n\n⚠️ ${parsed.message}`;
							break;
						}
						case "done": {
							msg.isStreaming = false;
							msg.content = msg.content
								.replace(/```sql\s*\n[\s\S]*?```/g, "")
								.replace(/```map\s*\n[\s\S]*?```/g, "")
								.replace(/[▀-▟]/g, "")
								.trim();
							break;
						}
					}
				},
				abortController.signal,
			);

			// Render map from server-provided data (spatial H3 queries) or execute in WASM
			const mapData = pendingMapData as Record<string, unknown>[] | null;
			if (mapData !== null) {
				const msg = messages.value[messages.value.length - 1];
				if (!msg) return;

				msg.queryResults = mapData;

				if (mapData.length > 0 && pendingMapPlan) {
					updateHexagons(mapData, pendingMapPlan);
				}
			} else if (
				pendingSql &&
				!/h3_grid_disk|h3_string_to_h3|h3_h3_to_string|h3_latlng_to_cell/.test(
					pendingSql,
				)
			) {
				const result = await executeQuery(pendingSql);

				const msg = messages.value[messages.value.length - 1];
				if (!msg) return;

				if (result.error) {
					msg.content += `\n\n⚠️ ${result.error}`;
				} else {
					msg.queryResults = result.data;

					if (pendingMapPlan && result.data.length > 0) {
						updateHexagons(result.data, pendingMapPlan);
					}
				}
			}
		} catch (e: any) {
			if (e.name !== "AbortError") {
				const msg = messages.value[messages.value.length - 1];
				if (msg) {
					msg.content += `\n\n⚠️ Verbindingsfout: ${e.message}`;
					msg.isStreaming = false;
				}
			}
		} finally {
			isStreaming.value = false;
			abortController = null;
		}
	}

	function stopStreaming() {
		abortController?.abort();
		isStreaming.value = false;
	}

	async function loadSession(id: string) {
		const session = await api.getSession(id);
		sessionId.value = session.id;
		messages.value = session.messages.map((m) => ({
			id: m.id,
			role: m.role,
			content: m.content,
			mapPlan: m.map_config ?? undefined,
			thinkingSummaries: m.thinking_steps ?? undefined,
			feedback: m.feedback
				? {
						rating: m.feedback.rating,
						comment: m.feedback.comment ?? null,
						updatedAt: m.feedback.updated_at,
					}
				: null,
		}));

		// Re-execute SQL for the last assistant message that has both sql and a map plan
		const lastWithMap = [...session.messages]
			.reverse()
			.find((m) => m.role === "assistant" && m.sql && m.map_config);
		if (lastWithMap?.sql && lastWithMap.map_config) {
			const result = await executeQuery(lastWithMap.sql);
			const msg = messages.value.find((m) => m.id === lastWithMap.id);
			if (msg) {
				if (result.error) {
					msg.content += `\n\n⚠️ ${result.error}`;
				} else {
					msg.queryResults = result.data;
					if (result.data.length > 0) {
						updateHexagons(result.data, lastWithMap.map_config);
					}
				}
			}
		}
	}

	function clearMessages() {
		messages.value = [];
		sessionId.value = null;
	}

	function setMessageFeedback(
		messageId: string,
		feedback: MessageFeedback | null,
	) {
		const msg = messages.value.find((m) => m.id === messageId);
		if (msg) msg.feedback = feedback;
	}

	return {
		messages,
		isStreaming,
		model,
		sessionId,
		sendMessage,
		stopStreaming,
		clearMessages,
		loadSession,
		setMessageFeedback,
	};
}
