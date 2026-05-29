const FORBIDDEN_KEYWORDS = [
	"INSERT",
	"UPDATE",
	"DELETE",
	"DROP",
	"ALTER",
	"CREATE",
	"TRUNCATE",
	"EXEC",
	"EXECUTE",
	"GRANT",
	"REVOKE",
	"COPY",
	"ATTACH",
	"DETACH",
];

export function sanitizeSQL(sql: string): {
	safe: boolean;
	query: string;
	error?: string;
} {
	const trimmed = sql.trim();

	const firstWord = trimmed.toUpperCase().split(/\s/)[0];
	if (firstWord !== "SELECT" && firstWord !== "WITH") {
		return {
			safe: false,
			query: trimmed,
			error: "Alleen SELECT queries zijn toegestaan.",
		};
	}

	const upper = trimmed.toUpperCase();
	for (const keyword of FORBIDDEN_KEYWORDS) {
		const pattern = new RegExp(`\\b${keyword}\\b`, "i");
		if (pattern.test(upper)) {
			return {
				safe: false,
				query: trimmed,
				error: `Verboden keyword gevonden: ${keyword}`,
			};
		}
	}

	return { safe: true, query: trimmed };
}
