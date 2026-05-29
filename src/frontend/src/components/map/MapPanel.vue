<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useMap } from "../../composables/useMap";
import MapLegend from "./MapLegend.vue";

const {
	legend,
	heightLegend,
	iconLegend,
	categoryLegend,
	tooltip,
	scaleMode,
	map,
	initMap,
} = useMap();

function onToggleScale() {
	scaleMode.value = scaleMode.value === "percentile" ? "linear" : "percentile";
}

function adjustPitch(delta: number) {
	if (!map.value) return;
	const current = map.value.getPitch();
	map.value.easeTo({
		pitch: Math.min(85, Math.max(0, current + delta)),
		duration: 300,
	});
}

const mapContainer = ref<HTMLElement | null>(null);

onMounted(() => {
	if (mapContainer.value) {
		initMap(mapContainer.value);
	}
});
</script>

<template>
  <div class="map-panel">
    <div ref="mapContainer" class="map-container" />
    <div class="pitch-controls">
      <button class="pitch-btn" title="Tilt up" @click="adjustPitch(15)">
        <svg viewBox="0 0 10 6" width="10" height="6"><path d="M1 5 L5 1 L9 5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <button class="pitch-btn" title="Tilt down" @click="adjustPitch(-15)">
        <svg viewBox="0 0 10 6" width="10" height="6"><path d="M1 1 L5 5 L9 1" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>
    <MapLegend
      v-if="legend || heightLegend || iconLegend || categoryLegend"
      :legend="legend"
      :height-legend="heightLegend"
      :icon-legend="iconLegend"
      :category-legend="categoryLegend"
      :scale-mode="scaleMode"
      @toggle-scale="onToggleScale"
    />
    <div
      v-if="tooltip"
      class="hex-tooltip"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
    >
      <div v-for="line in tooltip.lines" :key="line.key" class="tooltip-line">
        <span class="tooltip-key">{{ line.key }}:</span> {{ line.value }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.map-panel {
  position: relative;
  width: 100%;
  height: 100%;
}

.map-container {
  width: 100%;
  height: 100%;
}

.opacity-control {
  position: absolute;
  bottom: 32px;
  right: 12px;
  background: white;
  border-radius: 8px;
  padding: 0.4rem 0.7rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.7rem;
  color: #374151;
}

.opacity-label {
  white-space: nowrap;
  font-weight: 600;
}

.opacity-value {
  min-width: 2.5rem;
  text-align: right;
  color: #6b7280;
}

input[type="range"] {
  width: 80px;
  accent-color: #3b82f6;
}

.pitch-controls {
  position: absolute;
  top: 110px;
  right: 10px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  z-index: 10;
}

.pitch-btn {
  width: 29px;
  height: 29px;
  background: white;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #333;
  padding: 0;
  box-shadow: 0 0 0 2px rgba(0,0,0,0.1);
  transition: background 0.1s;
}

.pitch-btn:hover {
  background: #f0f0f0;
}

.hex-tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.8);
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
  transform: translate(-50%, -100%);
  margin-top: -8px;
  width: max-content;
  max-width: 90vw;
  z-index: 10;
}

.tooltip-line {
  line-height: 1.4;
  word-break: break-word;
}

.tooltip-key {
  font-weight: 600;
  opacity: 0.8;
}
</style>
