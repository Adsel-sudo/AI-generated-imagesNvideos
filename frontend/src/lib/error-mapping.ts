export type ErrorScene =
  | "empty_request"
  | "optimize_failed"
  | "submit_failed"
  | "generation_failed"
  | "network_error"
  | "upload_failed"
  | "result_failed"
  | "timeout";

const ERROR_MESSAGE_MAP: Record<ErrorScene, string> = {
  empty_request: "请先输入你的需求，再开始生成。",
  optimize_failed: "需求整理暂时失败了，请稍后再试。",
  submit_failed: "任务提交未成功，请稍后重试。",
  generation_failed: "图片生成失败，建议调整描述后再试一次。",
  network_error: "网络连接不稳定，请检查网络后重试。",
  upload_failed: "参考图上传失败，请稍后重试。",
  result_failed: "结果暂时获取失败，请稍后刷新查看。",
  timeout: "处理时间较长，请稍后在当前对话中继续查看。",
};

const extractErrorText = (error: unknown): string => {
  if (!error) return "";

  if (typeof error === "string") return error.toLowerCase();

  if (error instanceof Error) {
    const message = error.message || "";
    const causeText =
      error.cause && typeof error.cause === "object" && "message" in error.cause
        ? String((error.cause as { message?: unknown }).message || "")
        : "";
    return `${message} ${causeText}`.toLowerCase();
  }

  if (typeof error === "object") {
    try {
      return JSON.stringify(error).toLowerCase();
    } catch {
      return "";
    }
  }

  return "";
};

const isNetworkError = (error: unknown): boolean => {
  const text = extractErrorText(error);
  if (!text) return false;

  return (
    text.includes("failed to fetch") ||
    text.includes("network") ||
    text.includes("load failed") ||
    text.includes("networkerror") ||
    text.includes("timeout") ||
    text.includes("econnrefused") ||
    text.includes("enotfound") ||
    text.includes("502") ||
    text.includes("503") ||
    text.includes("504")
  );
};

export const getFriendlyErrorMessage = (scene: ErrorScene, error?: unknown): string => {
  if (error) {
    console.error(`[${scene}]`, error);
  }

  if (error && isNetworkError(error)) {
    return ERROR_MESSAGE_MAP.network_error;
  }

  return ERROR_MESSAGE_MAP[scene];
};
