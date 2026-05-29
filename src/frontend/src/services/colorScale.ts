// Diverging color scale: purple (negative) ← white (zero) → blue (positive)
// 5 stops each, evenly sampled from the original ColorBrewer-derived 4-stop palettes.
// Index 0 = near zero (lightest), index 4 = furthest from zero (darkest).
const PURPLE_COLORS: [number, number, number, number][] = [
	[242, 240, 247, 180],
	[213, 211, 231, 180],
	[181, 178, 213, 190],
	[145, 136, 191, 210],
	[106, 81, 163, 240],
];

const BLUE_COLORS: [number, number, number, number][] = [
	[239, 243, 255, 180],
	[140, 191, 224, 180],
	[70, 144, 198, 190],
	[27, 97, 163, 210],
	[8, 48, 107, 240],
];

const ZERO_COLOR: [number, number, number, number] = [255, 255, 255, 180];

export const NUM_CLASSES = 5;

// Fraction of the color scale reserved for outliers beyond the percentile bounds.
// e.g. 0.12 means P2–P98 uses t∈[0, 0.88], outliers use t∈[0.88, 1].
const OUTLIER_FRACTION = 0.12;

// Maps an absolute value on one half-axis to t ∈ [0, 1].
// Values within percentileBound → t ∈ [0, 1 - OUTLIER_FRACTION]  (main range)
// Values beyond percentileBound → t ∈ [1 - OUTLIER_FRACTION, 1]  (compressed outlier tail)
function normalizeHalfAxis(
	absValue: number,
	absPercentileBound: number,
	absDataBound: number,
): number {
	if (absValue <= absPercentileBound) {
		return absPercentileBound > 0
			? Math.min(1, absValue / absPercentileBound) * (1 - OUTLIER_FRACTION)
			: 0;
	}
	const outlierRange = absDataBound - absPercentileBound;
	const frac =
		outlierRange > 0
			? Math.min(1, (absValue - absPercentileBound) / outlierRange)
			: 1;
	return 1 - OUTLIER_FRACTION + frac * OUTLIER_FRACTION;
}

function classIndex(t: number): number {
	return Math.min(Math.floor(t * NUM_CLASSES), NUM_CLASSES - 1);
}

export function computePercentile(sorted: number[], p: number): number {
	if (sorted.length === 0) return 0;
	const index = (p / 100) * (sorted.length - 1);
	const lo = Math.floor(index);
	const hi = Math.ceil(index);
	return sorted[lo]! + (sorted[hi]! - sorted[lo]!) * (index - lo);
}

// scaleMin/scaleMax are the effective scale bounds (P2/P98 in percentile mode, or data min/max in linear mode).
// dataMin/dataMax are the actual data bounds; when they differ from scale bounds, outlier
// compression is applied so extreme values remain visually distinct from the percentile boundary.
export function getColor(
	value: number,
	scaleMin: number,
	scaleMax: number,
	dataMin: number = scaleMin,
	dataMax: number = scaleMax,
): [number, number, number, number] {
	if (value === 0) return ZERO_COLOR;

	const hasOutliers = dataMin < scaleMin || dataMax > scaleMax;

	if (!hasOutliers) {
		// Linear mode or data fits within scale: clamp and map full range
		const extent = Math.max(Math.abs(scaleMin), Math.abs(scaleMax));
		if (extent === 0) return BLUE_COLORS[0]!;
		const clamped = Math.max(scaleMin, Math.min(scaleMax, value));
		if (clamped > 0) {
			return BLUE_COLORS[classIndex(clamped / extent)]!;
		} else {
			return PURPLE_COLORS[classIndex(-clamped / extent)]!;
		}
	}

	// Percentile mode with outlier compression: normalize each half-axis independently
	if (value > 0) {
		const t = normalizeHalfAxis(value, Math.abs(scaleMax), Math.abs(dataMax));
		return BLUE_COLORS[classIndex(t)]!;
	} else {
		const t = normalizeHalfAxis(-value, Math.abs(scaleMin), Math.abs(dataMin));
		return PURPLE_COLORS[classIndex(t)]!;
	}
}

export interface LegendClass {
	color: [number, number, number, number];
	rangeMin: number;
	rangeMax: number;
	isZero?: boolean;
}

// Returns ordered legend classes: darkest negative → lightest negative → zero → lightest positive → darkest positive
export function getLegendClasses(
	scaleMin: number,
	scaleMax: number,
	hasZeroValues: boolean,
): LegendClass[] {
	if (scaleMin === scaleMax) return [];

	const classes: LegendClass[] = [];

	if (scaleMin < 0) {
		// Iterate from darkest (class 4, most negative) to lightest (class 0, near zero)
		for (let i = NUM_CLASSES - 1; i >= 0; i--) {
			classes.push({
				color: PURPLE_COLORS[i]!,
				rangeMin: (scaleMin * (i + 1)) / NUM_CLASSES,
				rangeMax: (scaleMin * i) / NUM_CLASSES,
			});
		}
	}

	if (hasZeroValues) {
		classes.push({ color: ZERO_COLOR, rangeMin: 0, rangeMax: 0, isZero: true });
	}

	if (scaleMax > 0) {
		// Iterate from lightest (class 0, near zero) to darkest (class 4, most positive)
		for (let i = 0; i < NUM_CLASSES; i++) {
			classes.push({
				color: BLUE_COLORS[i]!,
				rangeMin: (scaleMax * i) / NUM_CLASSES,
				rangeMax: (scaleMax * (i + 1)) / NUM_CLASSES,
			});
		}
	}

	return classes;
}

function hashString(s: string): number {
	let hash = 0;
	for (let i = 0; i < s.length; i++) {
		hash = (Math.imul(31, hash) + s.charCodeAt(i)) | 0;
	}
	return Math.abs(hash);
}

function hslToRgba(
	h: number,
	s: number,
	l: number,
): [number, number, number, number] {
	s /= 100;
	l /= 100;
	const a = s * Math.min(l, 1 - l);
	const f = (n: number) => {
		const k = (n + h / 30) % 12;
		return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
	};
	return [
		Math.round(f(0) * 255),
		Math.round(f(8) * 255),
		Math.round(f(4) * 255),
		200,
	];
}

export function getCategoryColor(
	value: string,
): [number, number, number, number] {
	const hash = hashString(value);
	const hue = (hash * 137) % 360;
	const saturation = 55 + (hash % 20);
	const lightness = 40 + (hash % 20);
	return hslToRgba(hue, saturation, lightness);
}
