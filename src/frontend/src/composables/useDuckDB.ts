import { ref } from "vue";
import { api } from "../services/api";
import { sanitizeSQL } from "../services/sqlSanitizer";

const isReady = ref(true);
const isLoading = ref(false);
const error = ref<string | null>(null);

async function init() {
	// No-op: queries now run server-side.
}

async function executeQuery(
	sql: string,
): Promise<{ data: Record<string, unknown>[]; error?: string }> {
	const check = sanitizeSQL(sql);
	if (!check.safe) {
		return { data: [], error: check.error };
	}

	try {
		const result = await api.runQuery(check.query);
		return { data: result.rows };
	} catch (e: any) {
		return { data: [], error: `Query fout: ${e.message}` };
	}
}

export function useDuckDB() {
	return {
		isReady,
		isLoading,
		error,
		init,
		executeQuery,
	};
}
