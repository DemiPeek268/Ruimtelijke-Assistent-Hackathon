export interface ThinkingSummary {
	step_id: string;
	summary?: string;
}

export const THINKING_STEP_LABELS: Record<string, string> = {
	intentie: "Begrijpen wat de intentie van je vraag is",
	validatie: "Controleren of de filterwaarden kloppen",
	sql: "Vertalen van de vraag naar een database-query",
	kaart: "Bepalen hoe de resultaten gevisualiseerd worden",
};

export interface MessageFeedback {
	rating: "up" | "down";
	comment?: string | null;
	updatedAt: string;
}

export interface ChatMessage {
	id: string;
	role: "user" | "assistant";
	content: string;
	sql?: string | null;
	mapPlan?: MapPlan;
	queryResults?: Record<string, unknown>[];
	isStreaming?: boolean;
	thinkingSummaries?: ThinkingSummary[];
	feedback?: MessageFeedback | null;
}

export interface ColorRole {
	column: string;
	label: string;
	kind: "numeric" | "categorical";
}

export interface HeightRole {
	column: string;
	label: string;
}

export interface IconRole {
	column: string;
	label: string;
}

export interface MapPlan {
	h3_column: string;
	color: ColorRole | null;
	height: HeightRole | null;
	icons?: IconRole[];
}

export interface ChatRequest {
	messages: { role: string; content: string }[];
	model: string;
}

export type SSEEventType =
	| "meta"
	| "text"
	| "map_config"
	| "map_data"
	| "error"
	| "status"
	| "step_thinking_summary"
	| "done";

export interface SSEEvent {
	event: SSEEventType;
	data: string;
}

// Session types

export interface SessionMessage {
	id: string;
	role: "user" | "assistant";
	content: string;
	sql?: string | null;
	map_config?: MapPlan | null;
	thinking_steps?: ThinkingSummary[] | null;
	created_at: string;
	feedback?: {
		rating: "up" | "down";
		comment?: string | null;
		updated_at: string;
	} | null;
}

export interface SessionSummary {
	id: string;
	title: string | null;
	created_at: string;
	updated_at: string;
}

export interface SessionDetail {
	id: string;
	title: string | null;
	messages: SessionMessage[];
	created_at: string;
	updated_at: string;
}
