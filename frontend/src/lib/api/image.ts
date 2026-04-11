import { getApiBaseUrl, request } from "@/src/lib/api/client";
import type { TaskDetail, TaskOutputsResponse } from "@/src/types/api";
import type {
  GenerateTaskRequestPayload,
  GenerateTaskResponse,
  OptimizeRequestPayload,
  OptimizeResponse,
} from "@/src/types/image";

export function optimizePrompt(payload: OptimizeRequestPayload) {
  return request<OptimizeResponse>("/api/prompt/optimize", {
    method: "POST",
    body: payload,
  });
}

export function generateImageTask(payload: GenerateTaskRequestPayload) {
  return request<GenerateTaskResponse>("/api/prompt/generate-task", {
    method: "POST",
    body: payload,
  });
}

export function getTaskDetail(taskId: string) {
  return request<TaskDetail>(`/api/tasks/${taskId}`);
}

export function getTaskOutputs(taskId: string, params?: { page?: number; page_size?: number }) {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  const qs = query.toString();
  const path = qs ? `/api/tasks/${taskId}/outputs?${qs}` : `/api/tasks/${taskId}/outputs`;
  return request<TaskOutputsResponse>(path);
}

export function cancelTask(taskId: string) {
  return request<TaskDetail>(`/api/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

export function getOutputDownloadUrl(taskId: string, outputId: string, params?: { download?: boolean }) {
  const url = new URL(`${getApiBaseUrl()}/api/tasks/${taskId}/outputs/${outputId}`);
  if (params?.download) {
    url.searchParams.set("download", "1");
  }
  return url.toString();
}
