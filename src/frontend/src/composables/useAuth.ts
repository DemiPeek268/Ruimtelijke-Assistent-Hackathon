import { ref } from "vue";

const isAuthenticated = ref(true);
const isLoading = ref(false);
const account = ref<{ name?: string; username?: string } | null>(null);
const error = ref<string | null>(null);

async function initialize(): Promise<void> {}

export async function getAccessToken(): Promise<string | null> {
	return null;
}

async function logout(): Promise<void> {}

export function useAuth() {
	return {
		isAuthenticated,
		isLoading,
		account,
		error,
		initialize,
		logout,
	};
}
