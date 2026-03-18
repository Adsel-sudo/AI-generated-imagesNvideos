import type { GenerationTarget, TaskDetail } from "@/src/types/api";

export interface UploadedReferenceFile {
  file_id?: string;
  role?: string;
  file_name?: string;
  mime_type?: string;
  width?: number;
  height?: number;
  [key: string]: unknown;
}

export interface OptimizeRequestPayload {
  request_text: string;
  size?: string;
  style?: string;
  references?: UploadedReferenceFile[];
  generation_targets?: GenerationTarget[];
  [key: string]: unknown;
}

export interface OptimizeResponse {
  task_id?: string;
  optimized_prompt_cn?: string;
  structured_summary?: string;
  references?: UploadedReferenceFile[];
  generation_targets?: GenerationTarget[];
  usage_options?: Record<string, unknown>;
  confirm_notes?: string[];
  params_json?: Record<string, unknown>;
  task?: TaskDetail;
  [key: string]: unknown;
}

export interface GenerateTaskRequestPayload {
  request_text: string;
  optimized_prompt_cn?: string;
  structured_summary?: string;
  size?: string;
  style?: string;
  references?: UploadedReferenceFile[];
  generation_targets?: GenerationTarget[];
  usage_options?: Record<string, unknown>;
  confirm_notes?: string[];
  [key: string]: unknown;
}

export interface GenerateTaskResponse {
  task_id: string;
  status?: string;
  task?: TaskDetail;
  [key: string]: unknown;
}
