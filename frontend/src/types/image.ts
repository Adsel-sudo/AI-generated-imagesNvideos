import type { GenerationTarget, TaskDetail } from "@/src/types/api";

export interface UploadedReferenceFile {
  file_path: string;
  role: string;
  file_name?: string;
  mime_type?: string;
  width?: number;
  height?: number;
  [key: string]: unknown;
}

export interface OptimizeRequestPayload {
  task_type: string;
  raw_request: string;
  references?: UploadedReferenceFile[];
  usage_options?: Record<string, unknown>;
  generation_targets?: GenerationTarget[];
  [key: string]: unknown;
}

export interface OptimizeResponse {
  task_id?: string;
  optimized_prompt_cn?: string;
  generation_prompt?: string;
  structured_summary?: Record<string, unknown>;
  references?: UploadedReferenceFile[];
  generation_targets?: GenerationTarget[];
  usage_options?: Record<string, unknown>;
  confirm_notes?: string[];
  params_json?: Record<string, unknown>;
  task?: TaskDetail;
  [key: string]: unknown;
}

export interface GenerateTaskRequestPayload {
  task_type: string;
  optimized_prompt_cn: string;
  generation_prompt: string;
  structured_summary: Record<string, unknown>;
  n_outputs?: number;
  references?: UploadedReferenceFile[];
  generation_targets?: GenerationTarget[];
  usage_options?: Record<string, unknown>;
  confirm_notes?: string[];
  [key: string]: unknown;
}

export interface GenerateTaskResponse {
  id?: string;
  task_id?: string;
  status?: string;
  task?: TaskDetail;
  [key: string]: unknown;
}
