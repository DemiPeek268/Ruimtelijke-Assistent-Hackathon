<script setup lang="ts">
import Header from "@pzh-temporary/vue-component-library/src/components/Header/Header.vue";
import { computed } from "vue";
import { useMeerInfo } from "../../composables/useMeerInfo";

const { meerInfoOpen, toggleMeerInfo } = useMeerInfo();

const links = computed(() => [
	{
		text: "Over",
		callback: () => {
			toggleMeerInfo();
		},
		class: meerInfoOpen.value ? "pzh-header--selected" : "",
	},
]);
</script>

<template>
  <Header
    title="Ruimtelijke Assistent"
    url-home="/"
    :is-nuxt-environment="false"
    :has-mobile-menu="false"
    :links="links"
  />
</template>

<style scoped>
</style>
