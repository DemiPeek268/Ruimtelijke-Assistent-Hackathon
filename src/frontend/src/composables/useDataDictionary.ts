import { ref } from "vue";
import { api } from "../services/api";
import type { DataDictionary } from "../types/dictionary";

const dictionary = ref<DataDictionary | null>(null);
const isLoading = ref(false);
const error = ref<string | null>(null);

async function fetchDictionary() {
	if (dictionary.value) return;
	isLoading.value = true;
	error.value = null;
	try {
		dictionary.value = await api.getDictionary();
	} catch (e: any) {
		console.error("Failed to load dictionary:", e);
		if (e?.status === 403) {
			error.value =
				e?.detail ||
				"U heeft geen toegang tot de Databricks-omgeving. Neem contact op met de beheerder.";
		} else {
			error.value =
				"Kon de data-bibliotheek niet laden. Probeer het later opnieuw.";
		}
	} finally {
		isLoading.value = false;
	}
}

export function useDataDictionary() {
	return {
		dictionary,
		isLoading,
		error,
		fetchDictionary,
	};
}
