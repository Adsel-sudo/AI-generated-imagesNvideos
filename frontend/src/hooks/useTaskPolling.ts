"use client";

import { useCallback, useEffect, useRef } from "react";
import { getTaskDetail } from "@/src/lib/api/image";
import { getFriendlyErrorMessage } from "@/src/lib/error-mapping";
import type { Conversation } from "@/src/types/conversation";
import type { GeneratedOutput } from "@/src/types/conversation";

const POLL_INTERVAL_MS = 2000;
const POLL_STALL_THRESHOLD_MS = 90000;
const POLL_STALL_NOTICE = "处理时间较长，请稍后在当前对话中继续查看（任务仍在进行）";
const TERMINAL_SUCCESS = new Set(["succeeded", "completed", "done"]);
const TERMINAL_FAILED = new Set(["failed"]);
const TERMINAL_CANCELLED = new Set(["cancelled"]);

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
    outputs?: Array<{ id: string; file_path?: string | null; file_name?: string | null }>,
  ) => GeneratedOutput[];
}) {
  const pollingTaskIdsRef = useRef<Set<string>>(new Set());
  const { conversations, updateMessageById, mapTaskOutputsToGeneratedOutputs } = params;

  const pollTaskAndSyncMessage = useCallback(async ({
    conversationId,
    messageId,
    taskId,
  }: {
    conversationId: string;
    messageId: string;
    taskId: string;
  }) => {
    let lastProgressCurrent = 0;
    let lastOutputCount = 0;
    let lastStatus = "";
    let lastActivityAt = Date.now();
    let stallNotified = false;

    while (true) {
      try {
        const task = await getTaskDetail(taskId);
        const status = String(task.status || "").toLowerCase();
        const parsedProgressCurrent = Number(task.progress_current ?? 0);
        const progressCurrent = Number.isFinite(parsedProgressCurrent) ? Math.max(0, parsedProgressCurrent) : 0;
        const parsedProgressTotal = Number(task.progress_total ?? task.n_outputs ?? 0);
        const progressTotal = Number.isFinite(parsedProgressTotal)
          ? Math.max(progressCurrent, parsedProgressTotal)
          : progressCurrent;
        const progressMessage =
          typeof task.progress_message === "string" && task.progress_message.trim()
            ? task.progress_message.trim()
            : undefined;

        const outputs = mapTaskOutputsToGeneratedOutputs(taskId, task.outputs);
        const outputCount = outputs.length;
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
        lastOutputCount = Math.max(lastOutputCount, outputCount);
        lastStatus = status;

        if (!TERMINAL_SUCCESS.has(status) && !TERMINAL_FAILED.has(status) && !TERMINAL_CANCELLED.has(status)) {
          const idleDuration = Date.now() - lastActivityAt;
          const isStalled = idleDuration >= POLL_STALL_THRESHOLD_MS;
          if (isStalled) {
            stallNotified = true;
          }

          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            progress_current: progressCurrent,
            progress_total: progressTotal,
            progress_message: isStalled
              ? POLL_STALL_NOTICE
              : progressMessage || (stallNotified ? POLL_STALL_NOTICE : message.progress_message),
            generated_outputs: outputs.length ? outputs : message.generated_outputs,
          }));

          await sleep(POLL_INTERVAL_MS);
          continue;
        }

        if (TERMINAL_SUCCESS.has(status)) {
          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            system_status: "done",
            progress_current: progressTotal || progressCurrent || message.progress_total || 0,
            progress_total: progressTotal || message.progress_total || 0,
            progress_message: progressMessage,
            generated_outputs: outputs.length
              ? outputs
              : message.generated_outputs.map((output) => ({
                  ...output,
                  status: "failed",
                })),
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
            generated_outputs: outputs.length ? outputs : message.generated_outputs,
          }));
          return;
        }

        if (TERMINAL_FAILED.has(status)) {
          const failedReasonRaw =
            typeof task.error_message === "string" && task.error_message.trim()
              ? task.error_message.trim()
              : getFriendlyErrorMessage("generation_failed");
          const failedReason = getFriendlyErrorMessage("generation_failed", failedReasonRaw);
          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            system_status: "error",
            error_message: failedReason,
            progress_current: progressCurrent || message.progress_current,
            progress_total: progressTotal || message.progress_total,
            progress_message: progressMessage,
            generated_outputs: message.generated_outputs.map((output) => ({
              ...output,
              status: "failed",
            })),
          }));
          return;
        }
      } catch (error) {
        updateMessageById(conversationId, messageId, (message) => ({
          ...message,
          system_status: "error",
          error_message: getFriendlyErrorMessage("result_failed", error),
          generated_outputs: message.generated_outputs.map((output) => ({
            ...output,
            status: "failed",
          })),
        }));
        return;
      }
    }
  }, [mapTaskOutputsToGeneratedOutputs, updateMessageById]);

  const startPollingTask = useCallback((task: { conversationId: string; messageId: string; taskId: string }) => {
    if (pollingTaskIdsRef.current.has(task.taskId)) {
      return;
    }
    pollingTaskIdsRef.current.add(task.taskId);
    void pollTaskAndSyncMessage(task).finally(() => {
      pollingTaskIdsRef.current.delete(task.taskId);
    });
  }, [pollTaskAndSyncMessage]);

  useEffect(() => {
    for (const conversation of conversations) {
      for (const message of conversation.messages) {
        if (message.system_status !== "processing" || !message.task_id) continue;
        startPollingTask({
          conversationId: conversation.conversation_id,
          messageId: message.id,
          taskId: message.task_id,
        });
      }
    }
  }, [conversations, startPollingTask]);

  return { startPollingTask };
}
