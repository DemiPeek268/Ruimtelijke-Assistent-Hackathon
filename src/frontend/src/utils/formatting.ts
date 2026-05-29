export function formatNumber(value: number): string {
	if (Number.isInteger(value)) {
		return value.toLocaleString("nl-NL");
	}
	return value.toLocaleString("nl-NL", { maximumFractionDigits: 2 });
}

export function generateId(): string {
	return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
