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
  empty_request: "请先填写原始需求。",
  optimize_failed: "需求整理失败，请稍后重试。",
  submit_failed: "任务提交失败，请稍后重试。",
  generation_failed: "生成失败，请调整需求后重试。",
  network_error: "网络异常，请检查网络后重试。",
  upload_failed: "参考图上传失败，请稍后重试。",
  result_failed: "结果获取失败，请稍后刷新查看。",
  timeout: "任务处理超时，请稍后在对话中重试。",
};

const isNetworkError = (error: unknown): boolean => {
  if (!(error instanceof Error)) return false;
  const text = error.message.toLowerCase();
  return (
    text.includes("failed to fetch") ||
    text.includes("network") ||
    text.includes("load failed") ||
    text.includes("networkerror")
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
