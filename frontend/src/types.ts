// Shapes returned by the FastAPI backend. These mirror api/main.py responses.

export interface QualityReport {
  original_shape: [number, number];
  final_shape: [number, number];
  encoding_used: string;
  duplicate_rows_removed: number;
  columns_renamed: Record<string, string>;
  date_columns_parsed: string[];
  numeric_columns_coerced: string[];
  categorical_columns_normalized: string[];
  missing_values_filled: Record<string, number>;
  missing_values_flagged: Record<string, number>;
  unparseable_dates: Record<string, number>;
  failed_numeric_coercions: Record<string, number>;
  anomalies: string[];
}

export interface Preview {
  columns: string[];
  rows: Record<string, string | number | null>[];
}

export interface Session {
  session_id: string;
  filename: string;
  rows: number;
  cols: number;
  quality: QualityReport;
  quality_markdown: string;
  preview: Preview;
  requests_used: number;
  requests_max: number;
}

export type Category = "trend" | "anomaly" | "comparison" | "correlation";
export type Verdict = "approve" | "downgrade";

export interface Insight {
  insight: string;
  supporting_data: string;
  category: Category;
  confidence: number;
  critic_verdict: Verdict;
  critic_reasoning: string;
}

export interface ChartPoint {
  label: string;
  value: number | null;
}

export interface ChartData {
  kind: "bar" | "line";
  title: string;
  x_label: string;
  y_label: string;
  points: ChartPoint[];
}

export interface QAResult {
  answer: string;
  chart: ChartData | null;
  requests_used: number;
}

export interface Metrics {
  total: number;
  success_rate: number | null;
  avg_latency: number | null;
  avg_confidence: number | null;
  confidence_series: number[];
}
