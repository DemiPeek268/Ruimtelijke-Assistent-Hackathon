export interface ColumnInfo {
	name: string;
	type: string;
	table: string;
	group: string;
	min?: string;
	max?: string;
	mean?: string;
	sample_values: string[];
	description: string;
	unit?: string;
	categorical: boolean;
}

export interface TableInfo {
	name: string;
	group: string;
	columns: ColumnInfo[];
}

export interface Theme {
	name: string;
	label: string;
	example_questions: string[];
	tables: TableInfo[];
}

export interface DataDictionary {
	total_rows: number;
	total_columns: number;
	themes: Theme[];
}
