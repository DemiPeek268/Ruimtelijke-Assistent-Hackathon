import { ref } from "vue";

const meerInfoOpen = ref(false);

export function useMeerInfo() {
	function toggleMeerInfo() {
		meerInfoOpen.value = !meerInfoOpen.value;
	}

	return {
		meerInfoOpen,
		toggleMeerInfo,
	};
}
