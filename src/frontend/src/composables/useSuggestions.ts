import { computed } from "vue";
import { useDataDictionary } from "./useDataDictionary";

export function useSuggestions() {
	const { dictionary } = useDataDictionary();

	const suggestions = computed(() => {
		if (!dictionary.value) return [];
		return dictionary.value.themes
			.filter((t) => t.example_questions.length > 0)
			.map((t) => ({
				theme: t.label,
				questions: t.example_questions.slice(0, 2),
			}));
	});

	const allQuestions = computed(() => {
		return suggestions.value.flatMap((s) => s.questions);
	});

	return {
		suggestions,
		allQuestions,
	};
}
