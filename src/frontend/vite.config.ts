import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const backendUrl = process.env.VITE_API_URL || "http://backend:8001";

export default defineConfig({
	plugins: [
		vue({
			template: {
				compilerOptions: {
					isCustomElement: (tag) => tag === "NuxtLink",
				},
			},
		}),
	],
	optimizeDeps: {
		exclude: ["@duckdb/duckdb-wasm"],
	},
	server: {
		port: 5173,
		host: "0.0.0.0",
		allowedHosts: true,
		proxy: {
			"/api": {
				target: backendUrl,
				changeOrigin: true,
			},
			"/healthcheck": {
				target: backendUrl,
				changeOrigin: true,
			},
		},
	},
});
