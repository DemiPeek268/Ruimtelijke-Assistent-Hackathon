import { cellToLatLng } from "h3-js";

export function getH3Bounds(h3Ids: string[]): {
	center: [number, number];
	zoom: number;
} {
	if (h3Ids.length === 0) {
		return { center: [4.5, 52.0], zoom: 9 };
	}

	let minLat = 90,
		maxLat = -90,
		minLng = 180,
		maxLng = -180;

	for (const id of h3Ids) {
		try {
			const [lat, lng] = cellToLatLng(id);
			minLat = Math.min(minLat, lat);
			maxLat = Math.max(maxLat, lat);
			minLng = Math.min(minLng, lng);
			maxLng = Math.max(maxLng, lng);
		} catch {
			// skip invalid h3 ids
		}
	}

	const centerLat = (minLat + maxLat) / 2;
	const centerLng = (minLng + maxLng) / 2;
	const latRange = maxLat - minLat;
	const lngRange = maxLng - minLng;
	const maxRange = Math.max(latRange, lngRange);

	// Rough zoom estimation
	let zoom = 9;
	if (maxRange < 0.01) zoom = 14;
	else if (maxRange < 0.05) zoom = 12;
	else if (maxRange < 0.1) zoom = 11;
	else if (maxRange < 0.3) zoom = 10;
	else if (maxRange < 1) zoom = 9;
	else if (maxRange < 3) zoom = 8;
	else zoom = 7;

	return { center: [centerLng, centerLat], zoom };
}
