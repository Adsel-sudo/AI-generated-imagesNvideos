export type TaskStatus =
  | "pending"
  | "queued"
  | "processing"
  | "running"
  | "succeeded"
  | "completed"
  | "done"
  | "failed"
  | "cancelled"
  | string;

export type TaskType = "image" | "prompt" | string;

export interface OutputItem {
  id: string;
  task_id: string;
  index?: number | null;
  file_path?: string | null;
  original_path?: string | null;
  preview_path?: string | null;
  thumbnail_path?: string | null;
  preview_url?: string | null;
  thumbnail_url?: string | null;
  lowres_url?: string | null;
  original_url?: string | null;
  mime_type?: string | null;
  file_name?: string | null;
  width?: number | null;
  height?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface GenerationTarget {
  target_type?: string;
  aspect_ratio?: string;
  label?: string;
  width?: number;
  height?: number;
  size?: string;
  n_outputs?: number;
  [key: string]: unknown;
}

export interface TaskParamsJson {
  optimized_prompt_cn?: string;
  structured_summary?: string;
  references?: Array<Record<string, unknown>>;
  generation_targets?: GenerationTarget[];
  usage_options?: Record<string, unknown>;
  confirm_notes?: string[];
  [key: string]: unknown;
}

export interface TaskDetail {
  id: string;
  status: TaskStatus;
  progress_current?: number | null;
  progress_total?: number | null;
  progress_percent?: number | null;
  message?: string | null;
  error?: string | null;
  output_count?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface TaskOutputsResponse {
  task_id: string;
  page: number;
  page_size: number;
  total: number;
  items: OutputItem[];
}
