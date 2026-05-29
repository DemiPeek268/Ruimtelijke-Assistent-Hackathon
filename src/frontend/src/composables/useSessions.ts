import { ref } from "vue";
import { api } from "../services/api";
import type { SessionSummary } from "../types/chat";

const sessions = ref<SessionSummary[]>([]);
const isLoading = ref(false);

export function useSessions() {
	async function fetchSessions() {
		isLoading.value = true;
		try {
			sessions.value = await api.getSessions();
		} catch (e) {
			console.error("Failed to fetch sessions:", e);
		} finally {
			isLoading.value = false;
		}
	}

	async function deleteSession(id: string) {
		try {
			await api.deleteSession(id);
			sessions.value = sessions.value.filter((s) => s.id !== id);
		} catch (e) {
			console.error("Failed to delete session:", e);
		}
	}

	return {
		sessions,
		isLoading,
		fetchSessions,
		deleteSession,
	};
}
