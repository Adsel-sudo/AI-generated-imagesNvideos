"use client";

import { useCallback, useEffect, useRef } from "react";
import { getTaskDetail, getTaskOutputs } from "@/src/lib/api/image";
import { getFriendlyErrorMessage } from "@/src/lib/error-mapping";
import type { Conversation } from "@/src/types/conversation";
import type { GeneratedOutput } from "@/src/types/conversation";

const ACTIVE_POLL_INTERVAL_MS = 5000;
const SLOW_POLL_INTERVAL_MS = 8000;
const HIDDEN_POLL_INTERVAL_MS = 15000;
const UNCHANGED_SLOWDOWN_THRESHOLD = 3;
const POLL_STALL_THRESHOLD_MS = 90000;
const POLL_STALL_NOTICE = "处理时间较长，请稍后在当前对话中继续查看（任务仍在进行）";
const MAX_CONSECUTIVE_POLL_ERRORS = 3;
const TASK_OUTPUTS_PAGE_SIZE = 30;
const TERMINAL_SUCCESS = new Set([
  "done",
  // 兼容历史/第三方状态
  "succeeded",
  "completed",
  "success",
  "finished",
  "complete",
]);
const TERMINAL_FAILED = new Set(["failed"]);
const TERMINAL_CANCELLED = new Set(["cancelled"]);
const ACTIVE_STATUSES = new Set([
  // 与后端 TaskStatus 对齐
  "queued",
  "running",
  "saving",
  // 兼容历史/第三方状态
  "pending",
  "processing",
]);

const sleep = (ms: number) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

export function useTaskPolling(params: {
  conversations: Conversation[];
  updateMessageById: (
    conversationId: string,
    messageId: string,
    updater: (message: Conversation["messages"][number]) => Conversation["messages"][number],
  ) => void;
  mapTaskOutputsToGeneratedOutputs: (
    taskId: string,
    outputs?: Array<{
      id: string;
      file_path?: string | null;
      file_name?: string | null;
      preview_url?: string | null;
      thumbnail_url?: string | null;
      lowres_url?: string | null;
      original_url?: string | null;
    }>,
  ) => GeneratedOutput[];
}) {
  const pollingTaskIdsRef = useRef<Set<string>>(new Set());
  const cancelledTaskIdsRef = useRef<Set<string>>(new Set());
  const isUnmountedRef = useRef(false);
  const { conversations, updateMessageById, mapTaskOutputsToGeneratedOutputs } = params;

  const pollTaskAndSyncMessage = useCallback(async ({
    conversationId,
    messageId,
    taskId,
    initialOutputs,
  }: {
    conversationId: string;
    messageId: string;
    taskId: string;
    initialOutputs?: GeneratedOutput[];
  }) => {
    let lastProgressCurrent = 0;
    let lastProgressTotal = 0;
    let lastOutputCount = 0;
    let lastStatus = "";
    let lastActivityAt = Date.now();
    let stallNotified = false;
    let unchangedCount = 0;
    let cachedOutputs: GeneratedOutput[] = initialOutputs ?? [];
    let consecutivePollErrors = 0;

    const getNextPollInterval = (status: string, unchanged: number) => {
      if (typeof document !== "undefined" && document.hidden) {
        return HIDDEN_POLL_INTERVAL_MS;
      }
      if (ACTIVE_STATUSES.has(status)) {
        return unchanged >= UNCHANGED_SLOWDOWN_THRESHOLD ? SLOW_POLL_INTERVAL_MS : ACTIVE_POLL_INTERVAL_MS;
      }
      return ACTIVE_POLL_INTERVAL_MS;
    };

    while (!isUnmountedRef.current) {
      if (cancelledTaskIdsRef.current.has(taskId)) return;
      try {
        const task = await getTaskDetail(taskId);
        if (cancelledTaskIdsRef.current.has(taskId)) return;
        consecutivePollErrors = 0;
        const status = String(task.status || "").toLowerCase();
        console.log("[poll status snapshot]", {
          taskId,
          status,
          outputCount: task.output_count,
          progressCurrent: task.progress_current,
          progressTotal: task.progress_total,
        });
        const parsedProgressCurrent = Number(task.progress_current ?? 0);
        const progressCurrent = Number.isFinite(parsedProgressCurrent) ? Math.max(0, parsedProgressCurrent) : 0;
        const parsedProgressTotal = Number(task.progress_total ?? 0);
        const progressTotal = Number.isFinite(parsedProgressTotal)
          ? Math.max(progressCurrent, parsedProgressTotal)
          : progressCurrent;
        const progressMessage =
          typeof task.message === "string" && task.message.trim()
            ? task.message.trim()
            : undefined;
        const parsedOutputCount = Number(task.output_count ?? 0);
        const outputCount = Number.isFinite(parsedOutputCount) ? Math.max(0, parsedOutputCount) : 0;
        const unchanged =
          status === lastStatus &&
          progressCurrent === lastProgressCurrent &&
          progressTotal === lastProgressTotal;
        unchangedCount = unchanged ? unchangedCount + 1 : 0;
        const hasActivity =
          progressCurrent > lastProgressCurrent ||
          outputCount > lastOutputCount ||
          (status !== lastStatus &&
            !TERMINAL_SUCCESS.has(status) &&
            !TERMINAL_FAILED.has(status) &&
            !TERMINAL_CANCELLED.has(status));

        if (hasActivity) {
          lastActivityAt = Date.now();
          stallNotified = false;
        }
        lastProgressCurrent = Math.max(lastProgressCurrent, progressCurrent);
        lastProgressTotal = Math.max(lastProgressTotal, progressTotal);
        lastOutputCount = Math.max(lastOutputCount, outputCount);
        lastStatus = status;

        const shouldSyncOutputs =
          outputCount > cachedOutputs.length || TERMINAL_SUCCESS.has(status) || TERMINAL_CANCELLED.has(status);
        const shouldFetchOutputs =
          shouldSyncOutputs &&
          (outputCount > 0 || TERMINAL_SUCCESS.has(status) || TERMINAL_CANCELLED.has(status));
        if (shouldFetchOutputs) {
          const outputRes = await getTaskOutputs(taskId, { page: 1, page_size: TASK_OUTPUTS_PAGE_SIZE });
          if (cancelledTaskIdsRef.current.has(taskId)) return;
          cachedOutputs = mapTaskOutputsToGeneratedOutputs(taskId, outputRes.items);
          lastOutputCount = Math.max(lastOutputCount, cachedOutputs.length);
          console.log("[poll raw outputRes]", outputRes);
          console.log("[poll raw items]", outputRes?.items);
          console.log("[poll mapped outputs]", cachedOutputs);
          console.log(
            "[poll mapped outputs urls]",
            cachedOutputs.map((item) => ({
              id: item.id,
              status: item.status,
              preview_url: item.preview_url,
              modal_preview_url: item.modal_preview_url,
              url: item.url,
            })),
          );
          console.log("[poll cachedOutputs.length]", cachedOutputs.length);
          console.log("[poll task status raw]", task.status);
          console.log("[poll task status normalized]", status);
        }

        const completedByProgress =
          cachedOutputs.length > 0 && progressTotal > 0 && progressCurrent >= progressTotal;
        const isTerminalSuccess = TERMINAL_SUCCESS.has(status) || completedByProgress;

        if (!isTerminalSuccess && !TERMINAL_FAILED.has(status) && !TERMINAL_CANCELLED.has(status)) {
          const idleDuration = Date.now() - lastActivityAt;
          const isStalled = idleDuration >= POLL_STALL_THRESHOLD_MS;
          if (isStalled) {
            stallNotified = true;
          }
          const syncedProgressCurrent = Math.max(progressCurrent, cachedOutputs.length);
          const syncedProgressTotal = Math.max(progressTotal, syncedProgressCurrent);

          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            progress_current: syncedProgressCurrent,
            progress_total: syncedProgressTotal,
            progress_message: isStalled
              ? POLL_STALL_NOTICE
              : progressMessage || (stallNotified ? POLL_STALL_NOTICE : message.progress_message),
            generated_outputs: cachedOutputs,
          }));

          await sleep(getNextPollInterval(status, unchangedCount));
          continue;
        }

        if (isTerminalSuccess) {
          const outputRes = await getTaskOutputs(taskId, { page: 1, page_size: TASK_OUTPUTS_PAGE_SIZE });
          if (cancelledTaskIdsRef.current.has(taskId)) return;
          cachedOutputs = mapTaskOutputsToGeneratedOutputs(taskId, outputRes.items);
          const finalOutputCount = Math.max(cachedOutputs.length, outputCount);
          const finalProgressTotal = Math.max(progressTotal, finalOutputCount);
          const finalProgressCurrent = Math.max(progressCurrent, finalOutputCount);
          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            system_status: "done",
            progress_current: finalProgressCurrent || message.progress_current || 0,
            progress_total: finalProgressTotal || message.progress_total || 0,
            progress_message: progressMessage,
            generated_outputs: cachedOutputs,
          }));
          return;
        }

        if (TERMINAL_CANCELLED.has(status)) {
          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            system_status: "cancelled",
            progress_current: progressCurrent || message.progress_current,
            progress_total: progressTotal || message.progress_total,
            progress_message: progressMessage || "已停止",
            generated_outputs: cachedOutputs,
          }));
          return;
        }

        if (TERMINAL_FAILED.has(status)) {
          const failedReasonRaw =
            typeof task.error === "string" && task.error.trim()
              ? task.error.trim()
              : getFriendlyErrorMessage("generation_failed");
          const failedReason = getFriendlyErrorMessage("generation_failed", failedReasonRaw);
          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            system_status: "error",
            error_message: failedReason,
            progress_current: progressCurrent || message.progress_current,
            progress_total: progressTotal || message.progress_total,
            progress_message: progressMessage,
            generated_outputs: cachedOutputs,
          }));
          return;
        }
      } catch (error) {
        if (cancelledTaskIdsRef.current.has(taskId)) return;
        consecutivePollErrors += 1;
        const reachedRetryLimit = consecutivePollErrors >= MAX_CONSECUTIVE_POLL_ERRORS;

        updateMessageById(conversationId, messageId, (message) => ({
          ...message,
          system_status: reachedRetryLimit ? "error" : "processing",
          error_message: reachedRetryLimit ? getFriendlyErrorMessage("result_failed", error) : message.error_message,
          generated_outputs: cachedOutputs,
        }));

        if (reachedRetryLimit) {
          return;
        }

        await sleep(ACTIVE_POLL_INTERVAL_MS);
      }
    }
  }, [mapTaskOutputsToGeneratedOutputs, updateMessageById]);

  const startPollingTask = useCallback((task: {
    conversationId: string;
    messageId: string;
    taskId: string;
    initialOutputs?: GeneratedOutput[];
  }) => {
    cancelledTaskIdsRef.current.delete(task.taskId);
    if (pollingTaskIdsRef.current.has(task.taskId)) {
      return;
    }
    pollingTaskIdsRef.current.add(task.taskId);
    void pollTaskAndSyncMessage(task).finally(() => {
      pollingTaskIdsRef.current.delete(task.taskId);
    });
  }, [pollTaskAndSyncMessage]);

  const stopPollingTask = useCallback((taskId: string) => {
    cancelledTaskIdsRef.current.add(taskId);
    pollingTaskIdsRef.current.delete(taskId);
  }, []);

  useEffect(() => {
    for (const conversation of conversations) {
      for (const message of conversation.messages) {
        if (message.system_status !== "processing" || !message.task_id) continue;
        startPollingTask({
          conversationId: conversation.conversation_id,
          messageId: message.id,
          taskId: message.task_id,
          initialOutputs: message.generated_outputs,
        });
      }
    }
  }, [conversations, startPollingTask]);

  useEffect(() => {
    isUnmountedRef.current = false;
    return () => {
      isUnmountedRef.current = true;
    };
  }, []);

  return { startPollingTask, stopPollingTask };
}
