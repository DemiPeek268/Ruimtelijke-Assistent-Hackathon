<script setup lang="ts">
import { onBeforeMount } from "vue";
import ChatPanel from "./components/chat/ChatPanel.vue";
import MeerInfoPage from "./components/info/MeerInfoPage.vue";
import AppHeader from "./components/layout/AppHeader.vue";
import SplitPane from "./components/layout/SplitPane.vue";
import MapPanel from "./components/map/MapPanel.vue";
import { useDataDictionary } from "./composables/useDataDictionary";
import { useDuckDB } from "./composables/useDuckDB";
import { useMeerInfo } from "./composables/useMeerInfo";

const { init: initDB } = useDuckDB();
const { fetchDictionary } = useDataDictionary();
const { meerInfoOpen } = useMeerInfo();

onBeforeMount(() => {
	initDB();
	fetchDictionary();
});
</script>

<template>
  <div class="app">
    <AppHeader />
    <MeerInfoPage v-if="meerInfoOpen" />
    <SplitPane v-else>
      <template #left>
        <ChatPanel />
      </template>
      <template #right>
        <MapPanel />
      </template>
    </SplitPane>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app :deep(.pzh-header) {
  position: relative;
  z-index: 1000;
}
</style>
