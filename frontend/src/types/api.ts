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

export type TaskType = "image" | "video" | "prompt" | string;

export interface OutputItem {
  id: string;
  task_id: string;
  file_path?: string | null;
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
  type: TaskType;
  request_text?: string | null;
  params_json?: TaskParamsJson | null;
  status: TaskStatus;
  n_outputs?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
  progress_message?: string | null;
  model_name?: string | null;
  prompt_final?: string | null;
  error_message?: string | null;
  outputs?: OutputItem[];
  created_at?: string;
  updated_at?: string;
}
