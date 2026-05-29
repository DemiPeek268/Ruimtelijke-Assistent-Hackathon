<script setup lang="ts">
import { computed } from "vue";
import type {
	CategoryLegendConfig,
	HeightLegendConfig,
	IconLegendConfig,
	LegendConfig,
} from "../../types/map";
import { formatNumber } from "../../utils/formatting";

const props = defineProps<{
	legend: LegendConfig | null;
	heightLegend?: HeightLegendConfig | null;
	iconLegend?: IconLegendConfig | null;
	categoryLegend?: CategoryLegendConfig | null;
	scaleMode: "linear" | "percentile";
}>();

const emit = defineEmits<{
	toggleScale: [];
}>();

function colorToCSS(c: [number, number, number, number]): string {
	return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${c[3] / 255})`;
}

const zeroPercent = computed(() => {
	if (!props.legend) return null;
	const { scaleMin, scaleMax, classes } = props.legend;
	if (scaleMin >= 0 || scaleMax <= 0) return null;
	const negCount = classes.filter((c) => !c.isZero && c.rangeMin < 0).length;
	// Center on the white zero segment when present; otherwise place at the boundary
	const offset = classes.some((c) => c.isZero) ? 0.5 : 0;
	return ((negCount + offset) / classes.length) * 100;
});

const hasColorOutliers = computed(
	() =>
		!!props.legend &&
		(props.legend.min < props.legend.scaleMin ||
			props.legend.max > props.legend.scaleMax),
);

const hasHeightOutliers = computed(
	() =>
		!!props.heightLegend &&
		(props.heightLegend.min < props.heightLegend.scaleMin ||
			props.heightLegend.max > props.heightLegend.scaleMax),
);
</script>

<template>
  <div class="map-legend">
    <template v-if="legend">
      <div class="legend-title">Kleur — {{ legend.label }}</div>
      <div class="legend-bar-wrap">
        <div class="legend-segments">
          <span
            v-for="(cls, i) in legend.classes"
            :key="i"
            class="legend-segment"
            :class="{
              'segment-first': i === 0,
              'segment-last': i === legend.classes.length - 1,
            }"
            :style="{ background: colorToCSS(cls.color) }"
          />
        </div>
        <div class="legend-labels">
          <span class="legend-label-min">{{ formatNumber(legend.scaleMin) }}</span>
          <span
            v-if="zeroPercent !== null"
            class="legend-label-zero"
            :style="{ left: zeroPercent + '%' }"
          >0</span>
          <span class="legend-label-max">{{ formatNumber(legend.scaleMax) }}</span>
        </div>
      </div>
      <div v-if="hasColorOutliers && scaleMode === 'percentile'" class="legend-range-note">
        P2–P98
      </div>
    </template>

    <div v-if="heightLegend" class="height-section" :class="{ 'has-color': !!legend }">
      <div class="legend-title">Hoogte — {{ heightLegend.label }}</div>
      <div class="height-bar-wrap">
        <div class="height-ramp" />
        <div class="height-labels">
          <span>{{ formatNumber(heightLegend.scaleMin) }}</span>
          <span v-if="hasHeightOutliers && scaleMode === 'percentile'" class="legend-range-note">
            P2–P98
          </span>
          <span>{{ formatNumber(heightLegend.scaleMax) }}</span>
        </div>
      </div>
    </div>

    <div v-if="legend || heightLegend" class="legend-footer">
      <span class="toggle-label" :class="{ active: scaleMode === 'linear' }">Linear</span>
      <button
        class="toggle-switch"
        :class="{ on: scaleMode === 'percentile' }"
        role="switch"
        :aria-checked="scaleMode === 'percentile'"
        :title="scaleMode === 'percentile' ? 'Switch to linear scale' : 'Switch to percentile scale (P2–P98)'"
        @click="emit('toggleScale')"
      >
        <span class="toggle-thumb" />
      </button>
      <span class="toggle-label" :class="{ active: scaleMode === 'percentile' }">P2–P98</span>
    </div>

    <div v-if="iconLegend" class="icon-section" :class="{ 'has-above': !!legend || !!heightLegend }">
      <div class="legend-title">Aanwezigheid</div>
      <div v-for="item in iconLegend.items" :key="item.label" class="icon-legend-row">
        <span class="icon-dot" :style="{ background: colorToCSS(item.color) }" />
        <span class="icon-label">{{ item.label }}</span>
      </div>
    </div>

    <div v-if="categoryLegend" class="category-section" :class="{ 'has-above': !!legend || !!heightLegend || !!iconLegend }">
      <div class="legend-title">{{ categoryLegend.label }}</div>
      <div v-for="item in categoryLegend.items" :key="item.label" class="category-legend-row">
        <span class="category-swatch" :style="{ background: colorToCSS(item.color) }" />
        <span class="category-label">{{ item.label }}</span>
      </div>
      <div v-if="categoryLegend.truncated" class="category-more">… en meer</div>
    </div>
  </div>
</template>

<style scoped>
.map-legend {
  position: absolute;
  bottom: 32px;
  left: 12px;
  background: white;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  z-index: 10;
  min-width: 180px;
}

.legend-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.4rem;
}

.legend-bar-wrap {
  position: relative;
}

.legend-segments {
  display: flex;
  height: 14px;
  border-radius: 3px;
  overflow: hidden;
}

.legend-segment {
  flex: 1;
  border-right: 1px solid rgba(255, 255, 255, 0.4);
}

.legend-segment.segment-last {
  border-right: none;
}

.legend-labels {
  position: relative;
  height: 1.1rem;
  margin-top: 0.2rem;
  font-size: 0.65rem;
  color: #6b7280;
}

.legend-label-min {
  position: absolute;
  left: 0;
}

.legend-label-max {
  position: absolute;
  right: 0;
}

.legend-label-zero {
  position: absolute;
  transform: translateX(-50%);
  color: #374151;
  font-weight: 600;
}

.legend-range-note {
  font-size: 0.55rem;
  color: #9ca3af;
  font-style: italic;
  margin-top: 0.15rem;
}

.legend-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  margin-top: 0.5rem;
}

.toggle-label {
  font-size: 0.6rem;
  color: #9ca3af;
  transition: color 0.2s, font-weight 0.1s;
  white-space: nowrap;
  user-select: none;
}

.toggle-label.active {
  color: #374151;
  font-weight: 600;
}

.toggle-switch {
  position: relative;
  width: 28px;
  height: 15px;
  background: #d1d5db;
  border: none;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.2s;
  padding: 0;
  flex-shrink: 0;
  outline: none;
}

.toggle-switch:focus-visible {
  box-shadow: 0 0 0 2px #3b82f6;
}

.toggle-switch.on {
  background: #3b82f6;
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 11px;
  height: 11px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  pointer-events: none;
}

.toggle-switch.on .toggle-thumb {
  transform: translateX(13px);
}

.height-section {
  margin-top: 0.3rem;
}

.height-section.has-color {
  margin-top: 0.7rem;
  padding-top: 0.5rem;
}

.height-bar-wrap {
  margin-top: 0.2rem;
}

.height-ramp {
  height: 12px;
  border-radius: 3px;
  background: linear-gradient(to right, #d1d5db, #374151);
}

.height-labels {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.65rem;
  color: #6b7280;
  margin-top: 0.2rem;
}

.icon-section {
  margin-top: 0.3rem;
}

.icon-section.has-above {
  margin-top: 0.7rem;
  padding-top: 0.5rem;
  border-top: 1px solid #e5e7eb;
}

.icon-legend-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.25rem;
}

.icon-dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50% 50% 50% 0;
  transform: rotate(-45deg);
  flex-shrink: 0;
}

.icon-label {
  font-size: 0.7rem;
  color: #374151;
}

.category-section {
  margin-top: 0.3rem;
}

.category-section.has-above {
  margin-top: 0.7rem;
  padding-top: 0.5rem;
  border-top: 1px solid #e5e7eb;
}

.category-legend-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.25rem;
}

.category-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.category-label {
  font-size: 0.7rem;
  color: #374151;
}

.category-more {
  font-size: 0.65rem;
  color: #9ca3af;
  margin-top: 0.25rem;
  font-style: italic;
}
</style>
