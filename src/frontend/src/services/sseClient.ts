import type { SSEEventType } from "../types/chat";

type SSECallback = (event: SSEEventType, data: string) => void;

export async function streamSSE(
	url: string,
	body: unknown,
	onEvent: SSECallback,
	signal?: AbortSignal,
): Promise<void> {
	const response = await fetch(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
		signal,
	});

	if (!response.ok) {
		throw new Error(`Chat request failed: ${response.status}`);
	}

	const reader = response.body!.getReader();
	const decoder = new TextDecoder();
	let buffer = "";
	let currentEvent: SSEEventType = "text";

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;

		buffer += decoder.decode(value, { stream: true });
		const lines = buffer.split("\n");
		buffer = lines.pop() || "";

		for (const rawLine of lines) {
			const line = rawLine.replace(/\r$/, "");
			if (line === "") {
				currentEvent = "text";
				continue;
			}
			if (line.startsWith("event:")) {
				currentEvent = line.slice(6).trim() as SSEEventType;
			} else if (line.startsWith("data:")) {
				const data = line.slice(5).trim();
				if (data) {
					onEvent(currentEvent, data);
				}
			}
		}
	}
}
