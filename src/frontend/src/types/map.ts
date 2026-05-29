import type { LegendClass } from "../services/colorScale";

export type { LegendClass };

export interface MapViewState {
	latitude: number;
	longitude: number;
	zoom: number;
	pitch?: number;
	bearing?: number;
}

export interface HexagonData {
	h3_id: string;
	value: number;
	properties: Record<string, unknown>;
	[key: string]: unknown;
}

export interface LegendConfig {
	label: string;
	min: number;
	max: number;
	scaleMin: number;
	scaleMax: number;
	classes: LegendClass[];
	scaleMode: "linear" | "percentile";
}

export interface HeightLegendConfig {
	label: string;
	min: number;
	max: number;
	scaleMin: number;
	scaleMax: number;
}

export interface IconLegendConfig {
	items: { label: string; color: [number, number, number, number] }[];
}

export interface CategoryLegendConfig {
	label: string;
	items: { label: string; color: [number, number, number, number] }[];
	truncated: boolean;
}
