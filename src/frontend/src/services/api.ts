import type { SessionDetail, SessionSummary } from "../types/chat";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export const api = {
	getBaseUrl: () => API_BASE,

	async getDictionary() {
		const res = await fetch(`${API_BASE}/api/dictionary`);
		if (!res.ok) {
			const err = new Error(
				`Dictionary fetch failed: ${res.status}`,
			) as Error & {
				status: number;
				detail?: string;
			};
			err.status = res.status;
			try {
				const body = await res.json();
				err.detail = body?.detail;
			} catch {
				// non-JSON body — fall back to the generic message
			}
			throw err;
		}
		return res.json();
	},

	async runQuery(sql: string): Promise<{ rows: Record<string, unknown>[] }> {
		const res = await fetch(`${API_BASE}/api/query`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ sql }),
		});
		if (!res.ok) {
			const body = await res.json().catch(() => ({}));
			throw new Error(body?.detail ?? `Query failed: ${res.status}`);
		}
		return res.json();
	},

	getChatUrl() {
		return `${API_BASE}/api/chat`;
	},

	async getSessions(): Promise<SessionSummary[]> {
		const res = await fetch(`${API_BASE}/api/sessions`);
		if (!res.ok) throw new Error(`Sessions fetch failed: ${res.status}`);
		return res.json();
	},

	async getSession(id: string): Promise<SessionDetail> {
		const res = await fetch(`${API_BASE}/api/sessions/${id}`);
		if (!res.ok) throw new Error(`Session fetch failed: ${res.status}`);
		return res.json();
	},

	async deleteSession(id: string): Promise<void> {
		const res = await fetch(`${API_BASE}/api/sessions/${id}`, {
			method: "DELETE",
		});
		if (!res.ok) throw new Error(`Session delete failed: ${res.status}`);
	},

	async postMessageFeedback(
		sessionId: string,
		messageId: string,
		rating: "up" | "down" | null,
		comment?: string | null,
	): Promise<{
		rating: "up" | "down" | null;
		comment: string | null;
		updated_at: string | null;
	}> {
		const body: Record<string, unknown> = { rating };
		if (comment !== undefined) body.comment = comment;
		const res = await fetch(
			`${API_BASE}/api/sessions/${sessionId}/messages/${messageId}/feedback`,
			{
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(body),
			},
		);
		if (!res.ok) throw new Error(`Feedback save failed: ${res.status}`);
		return res.json();
	},
};
