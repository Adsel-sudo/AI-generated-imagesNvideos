import { getApiBaseUrl, request } from "@/src/lib/api/client";
import type { TaskDetail } from "@/src/types/api";
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

export function cancelTask(taskId: string) {
  return request<TaskDetail>(`/api/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

export function getOutputDownloadUrl(taskId: string, outputId: string) {
  return `${getApiBaseUrl()}/api/tasks/${taskId}/outputs/${outputId}`;
}
