"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import {
  generateImageTask,
  getOutputDownloadUrl,
  getTaskDetail,
  optimizePrompt,
} from "@/src/lib/api/image";
import { uploadFile } from "@/src/lib/api/files";
import {
  createConversation,
  createMessage,
  persistConversationState,
  loadConversationState,
} from "@/src/lib/conversation/session";
import {
  buildGeneratePayload,
  buildOptimizePayload,
} from "@/src/lib/conversation/payload";
import { getFriendlyErrorMessage } from "@/src/lib/error-mapping";
import type { Conversation } from "@/src/types/conversation";
import {
  createEmptyWorkbenchDraft,
  type ReferenceCategory,
  type WorkbenchDraft,
} from "@/src/types/workbench";

type SizeOption = "1600x1600" | "1464x600" | "600x450" | "other";

const PRESET_SIZES = ["1600x1600", "1464x600", "600x450"] as const;
const REFERENCE_GROUPS: Array<{ label: string; key: ReferenceCategory }> = [
  { label: "商品图", key: "product" },
  { label: "元素/构图参考图", key: "composition" },
  { label: "姿势参考图", key: "pose" },
  { label: "风格参考图", key: "style" },
];
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 30;

const getSizeDisplayText = (size: string) => {
  if (size === "1600x1600") return "1600 × 1600";
  if (size === "1464x600") return "1464 × 600";
  if (size === "600x450") return "600 × 450";
  return size.trim() || "（未填写）";
};

const TERMINAL_SUCCESS = new Set(["succeeded", "completed"]);
const TERMINAL_FAILED = new Set(["failed", "cancelled"]);

const sleep = (ms: number) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

function SendIcon({ disabled }: { disabled: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`h-5 w-5 ${disabled ? "text-slate-400" : "text-white"}`}
      aria-hidden="true"
    >
      <path
        d="M4 12L20 4L13 20L10.5 13.5L4 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LoadingIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="h-5 w-5 animate-spin text-slate-400"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
      <path d="M20 12a8 8 0 0 0-8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function getMessageStatusBadge(status: Conversation["messages"][number]["system_status"]) {
  if (status === "done") {
    return "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200";
  }
  if (status === "error") {
    return "bg-rose-50 text-rose-700 ring-1 ring-rose-200";
  }
  return "bg-amber-50 text-amber-700 ring-1 ring-amber-200";
}

export default function ImageWorkbenchPage() {
  const [sessionId, setSessionId] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>("");

  const [draft, setDraft] = useState<WorkbenchDraft>(createEmptyWorkbenchDraft());
  const [customSizeInput, setCustomSizeInput] = useState("");

  const [optimizeLoading, setOptimizeLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [optimizeError, setOptimizeError] = useState<string | null>(null);
  const [uploadingMap, setUploadingMap] = useState<Record<ReferenceCategory, boolean>>({
    product: false,
    composition: false,
    pose: false,
    style: false,
  });

  const selectedSizeOption: SizeOption = useMemo(() => {
    if (PRESET_SIZES.includes(draft.size as (typeof PRESET_SIZES)[number])) {
      return draft.size as SizeOption;
    }
    return "other";
  }, [draft.size]);

  const activeConversation = useMemo(
    () => conversations.find((item) => item.conversation_id === activeConversationId) ?? null,
    [activeConversationId, conversations],
  );

  useEffect(() => {
    const state = loadConversationState();
    setSessionId(state.session_id);
    setConversations(state.conversations);
    setActiveConversationId(state.active_conversation_id);
  }, []);

  useEffect(() => {
    if (!sessionId || !activeConversationId || !conversations.length) return;
    persistConversationState({
      session_id: sessionId,
      active_conversation_id: activeConversationId,
      conversations,
    });
  }, [activeConversationId, conversations, sessionId]);

  const handleNewConversation = () => {
    const conversation = createConversation();
    setConversations((prev) => [conversation, ...prev]);
    setActiveConversationId(conversation.conversation_id);
    setDraft((prev) => ({
      ...prev,
      reserved: {
        ...prev.reserved,
        conversation_id: conversation.conversation_id,
      },
    }));
  };

  const updatePreserveProductFidelity = (nextDraft: WorkbenchDraft): WorkbenchDraft => ({
    ...nextDraft,
    preserve_product_fidelity: nextDraft.references.product.length > 0,
  });

  const handleUploadFiles = async (category: ReferenceCategory, files: FileList | null) => {
    if (!files?.length) return;

    setUploadingMap((prev) => ({ ...prev, [category]: true }));
    setOptimizeError(null);

    try {
      const uploadedAssets = await Promise.all(
        Array.from(files).map(async (file) => {
          const uploaded = await uploadFile(file);
          return {
            local_id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
            file_id: uploaded.file_id,
            file_name: uploaded.file_name || file.name,
            mime_type: uploaded.mime_type || file.type,
            preview_url: URL.createObjectURL(file),
          };
        }),
      );

      setDraft((prev) =>
        updatePreserveProductFidelity({
          ...prev,
          references: {
            ...prev.references,
            [category]: [...prev.references[category], ...uploadedAssets],
          },
        }),
      );
    } catch (error) {
      setOptimizeError(getFriendlyErrorMessage("upload_failed", error));
    } finally {
      setUploadingMap((prev) => ({ ...prev, [category]: false }));
    }
  };

  const handleDropFiles = (category: ReferenceCategory, files: FileList | null) => {
    if (!files?.length) return;
    void handleUploadFiles(category, files);
  };

  const handleRemoveReference = (category: ReferenceCategory, localId: string) => {
    setDraft((prev) => {
      const target = prev.references[category].find((item) => item.local_id === localId);
      if (target?.preview_url.startsWith("blob:")) {
        URL.revokeObjectURL(target.preview_url);
      }

      return updatePreserveProductFidelity({
        ...prev,
        references: {
          ...prev.references,
          [category]: prev.references[category].filter((item) => item.local_id !== localId),
        },
      });
    });
  };

  const updateMessageById = (
    conversationId: string,
    messageId: string,
    updater: (message: Conversation["messages"][number]) => Conversation["messages"][number],
  ) => {
    setConversations((prev) =>
      prev.map((conversation) => {
        if (conversation.conversation_id !== conversationId) return conversation;
        return {
          ...conversation,
          updated_at: Date.now(),
          messages: conversation.messages.map((message) =>
            message.id === messageId ? updater(message) : message,
          ),
        };
      }),
    );
  };

  const pollTaskAndSyncMessage = async ({
    conversationId,
    messageId,
    taskId,
  }: {
    conversationId: string;
    messageId: string;
    taskId: string;
  }) => {
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
      try {
        const task = await getTaskDetail(taskId);
        const status = String(task.status || "").toLowerCase();

        if (TERMINAL_SUCCESS.has(status)) {
          const outputs =
            task.outputs?.map((output) => {
              const downloadUrl = getOutputDownloadUrl(output.id);
              return {
                id: output.id,
                kind: "image" as const,
                url: downloadUrl,
                downloadUrl,
                status: "ready" as const,
              };
            }) ?? [];

          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            system_status: "done",
            generated_outputs: outputs.length
              ? outputs
              : message.generated_outputs.map((output) => ({
                  ...output,
                  status: "failed",
                })),
          }));
          return;
        }

        if (TERMINAL_FAILED.has(status)) {
          updateMessageById(conversationId, messageId, (message) => ({
            ...message,
            system_status: "error",
            error_message: getFriendlyErrorMessage("generation_failed"),
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

      await sleep(POLL_INTERVAL_MS);
    }

    updateMessageById(conversationId, messageId, (message) => ({
      ...message,
      system_status: "error",
      error_message: getFriendlyErrorMessage("timeout"),
      generated_outputs: message.generated_outputs.map((output) => ({
        ...output,
        status: "failed",
      })),
    }));
  };

  const handleSubmitTask = async () => {
    if (!draft.raw_request.trim()) {
      setOptimizeError(getFriendlyErrorMessage("empty_request"));
      return;
    }

    let selectedConversationId = activeConversationId;

    if (!selectedConversationId) {
      const conversation = createConversation();
      selectedConversationId = conversation.conversation_id;
      setConversations((prev) => [conversation, ...prev]);
      setActiveConversationId(selectedConversationId);
    }

    const currentDraft: WorkbenchDraft = {
      ...draft,
      reserved: {
        ...draft.reserved,
        session_id: sessionId,
        conversation_id: selectedConversationId,
      },
    };

    setOptimizeError(null);
    setOptimizeLoading(true);
    setIsSubmitting(true);

    let optimizedPromptCn: string | undefined;
    let generationPrompt = "";
    let structuredSummary: Record<string, unknown> = {};

    try {
      const optimizeRes = await optimizePrompt(
        buildOptimizePayload({
          draft: currentDraft,
        }),
      );

      const optimized = optimizeRes.optimized_prompt_cn?.trim();
      optimizedPromptCn = optimized || undefined;
      generationPrompt = typeof optimizeRes.generation_prompt === "string" ? optimizeRes.generation_prompt : "";
      structuredSummary =
        optimizeRes.structured_summary && typeof optimizeRes.structured_summary === "object"
          ? optimizeRes.structured_summary
          : {};
    } catch (error) {
      setOptimizeError(getFriendlyErrorMessage("optimize_failed", error));
    } finally {
      setOptimizeLoading(false);
    }

    const message = createMessage({
      user_input: currentDraft.raw_request.trim(),
      system_status: "processing",
      optimized_prompt: optimizedPromptCn,
      size_text: getSizeDisplayText(currentDraft.size),
      style_preference: currentDraft.style_preference.trim() || undefined,
    });

    setConversations((prev) =>
      prev.map((conversation) => {
        if (conversation.conversation_id !== selectedConversationId) return conversation;

        const nextTitle =
          conversation.messages.length === 0
            ? currentDraft.raw_request.trim().slice(0, 16) || "新对话"
            : conversation.title;

        return {
          ...conversation,
          title: nextTitle,
          updated_at: Date.now(),
          messages: [...conversation.messages, message],
        };
      }),
    );

    try {
      const generateRes = await generateImageTask(
        buildGeneratePayload({
          draft: currentDraft,
          optimized_prompt_cn: optimizedPromptCn || currentDraft.raw_request,
          generation_prompt: generationPrompt || optimizedPromptCn || currentDraft.raw_request,
          structured_summary: structuredSummary,
        }),
      );

      const taskId = generateRes.id || generateRes.task_id || generateRes.task?.id;
      if (!taskId) {
        throw new Error("missing_task_id");
      }

      updateMessageById(selectedConversationId, message.id, (item) => ({
        ...item,
        task_id: taskId,
      }));

      void pollTaskAndSyncMessage({
        conversationId: selectedConversationId,
        messageId: message.id,
        taskId,
      });
      setDraft((prev) => ({ ...prev, raw_request: "" }));
    } catch (error) {
      const errorMessage = getFriendlyErrorMessage("submit_failed", error);
      setOptimizeError(errorMessage);

      updateMessageById(selectedConversationId, message.id, (item) => ({
        ...item,
        system_status: "error",
        error_message: errorMessage,
        generated_outputs: item.generated_outputs.map((output) => ({
          ...output,
          status: "failed",
        })),
      }));
    } finally {
      setIsSubmitting(false);
    }
  };

  const sending = optimizeLoading || isSubmitting;
  const canSend = draft.raw_request.trim().length > 0 && !sending;

  return (
    <main className="h-dvh bg-slate-100/80 px-2.5 py-1.5 sm:px-3 sm:py-2.5">
      <div className="mx-auto grid h-full w-full max-w-[1480px] grid-cols-1 gap-1.5 lg:grid-cols-[380px_minmax(0,1fr)_220px]">
        <aside className="order-2 flex min-h-0 flex-col rounded-2xl border border-slate-200/80 bg-white/70 shadow-[0_8px_24px_rgba(30,41,59,0.06)] backdrop-blur lg:order-1">
          <div className="flex-1 space-y-2.5 overflow-y-auto p-2.5">
            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">尺寸选择</div>
              <div className="grid grid-cols-2 gap-1.5 text-sm text-slate-700">
                {[
                  { label: "1600 × 1600", value: "1600x1600" as const },
                  { label: "1464 × 600", value: "1464x600" as const },
                  { label: "600 × 450", value: "600x450" as const },
                  { label: "其他", value: "other" as const },
                ].map((option) => (
                  <label
                    key={option.value}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-100/70 px-2 py-1"
                  >
                    <input
                      type="radio"
                      name="size"
                      className="h-4 w-4 border-slate-300 text-violet-600 focus:ring-violet-300"
                      checked={selectedSizeOption === option.value}
                      onChange={() => {
                        if (option.value === "other") {
                          const nextCustom = customSizeInput.trim();
                          setDraft((prev) => ({
                            ...prev,
                            size: nextCustom || prev.size,
                          }));
                          return;
                        }
                        setDraft((prev) => ({ ...prev, size: option.value }));
                      }}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
              {selectedSizeOption === "other" ? (
                <input
                  className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-violet-200"
                  placeholder="例如：1200 × 628"
                  value={customSizeInput || draft.size}
                  onChange={(e) => {
                    const value = e.target.value;
                    setCustomSizeInput(value);
                    setDraft((prev) => ({ ...prev, size: value }));
                  }}
                />
              ) : null}
            </div>

            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">风格需求</div>
              <input
                className="w-full rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-violet-200"
                placeholder="例：清爽、明亮、度假感、夏日氛围"
                value={draft.style_preference}
                onChange={(e) =>
                  setDraft((prev) => ({
                    ...prev,
                    style_preference: e.target.value,
                  }))
                }
              />
            </div>

            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">参考图片</div>
              <div className="space-y-2">
                {REFERENCE_GROUPS.map((item) => {
                  const category = item.key;
                  return (
                    <div key={item.key} className="space-y-1">
                      <div className="text-xs font-medium text-slate-600">{item.label}</div>
                      <label
                        className="block cursor-pointer rounded-xl border border-dashed border-slate-300 bg-white/80 px-2.5 py-2.5 text-center text-xs text-slate-500 transition hover:border-violet-300 hover:text-violet-600"
                        onDragOver={(event) => {
                          event.preventDefault();
                        }}
                        onDrop={(event) => {
                          event.preventDefault();
                          handleDropFiles(category, event.dataTransfer.files);
                        }}
                      >
                        {uploadingMap[category] ? "上传中..." : "点击或拖拽上传"}
                        <input
                          type="file"
                          accept="image/*"
                          multiple
                          className="hidden"
                          onChange={(e) => {
                            void handleUploadFiles(category, e.target.files);
                            e.target.value = "";
                          }}
                        />
                      </label>

                      {draft.references[category].length ? (
                        <div className="flex flex-wrap gap-1">
                          {draft.references[category].map((asset) => (
                            <div key={asset.local_id} className="group relative">
                              <Image
                                src={asset.preview_url}
                                alt={asset.file_name || "参考图"}
                                width={84}
                                height={84}
                                className="h-16 w-16 rounded-lg border border-slate-200 object-cover"
                                unoptimized
                              />
                              <button
                                type="button"
                                className="absolute -right-1 -top-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] text-white opacity-90 hover:bg-rose-600"
                                onClick={() => handleRemoveReference(category, asset.local_id)}
                                aria-label={`删除${item.label}`}
                              >
                                ×
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </aside>

        <section className="order-1 flex min-h-0 flex-col rounded-2xl border border-slate-200/80 bg-white/75 backdrop-blur shadow-[0_1px_2px_rgba(15,23,42,0.03)] lg:order-2">
          <div className="flex-1 space-y-2.5 overflow-y-auto px-3 py-3 sm:px-4">
            {activeConversation?.messages.length ? (
              activeConversation.messages.map((message) => (
                <article key={message.id} className="space-y-2">
                  <div className="ml-auto max-w-[68%] rounded-2xl bg-violet-600 px-3 py-2 text-sm text-white shadow-sm">
                    {message.user_input}
                  </div>

                  <div className="max-w-[78%] space-y-1.5 rounded-2xl border border-slate-200 bg-slate-100/60 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${getMessageStatusBadge(
                          message.system_status,
                        )}`}
                      >
                        {message.system_status === "done"
                          ? "生成完成"
                          : message.system_status === "error"
                            ? "生成失败"
                            : "生成中"}
                      </span>
                      {message.optimized_prompt ? (
                        <details className="max-w-[72%] rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-right">
                          <summary className="cursor-pointer text-xs font-medium text-slate-600">
                            查看优化后的提示词
                          </summary>
                          <div className="mt-1 text-left text-xs text-slate-500">{message.optimized_prompt}</div>
                        </details>
                      ) : null}
                    </div>

                    {message.error_message ? (
                      <div className="text-xs text-rose-600">{message.error_message}</div>
                    ) : null}

                    <div className="grid gap-1.5 sm:grid-cols-2">
                      {message.generated_outputs.map((output) => (
                        <div
                          key={output.id}
                          className="flex flex-col rounded-lg border border-slate-200 bg-white p-1.5"
                        >
                          <div className="aspect-[4/3] w-full rounded-md border border-dashed border-slate-200 bg-slate-100/70" />
                          <div className="mt-1.5 text-[11px] text-slate-500">
                            状态：
                            {output.status === "ready"
                              ? "可下载"
                              : output.status === "failed"
                                ? "失败"
                                : "待结果"}
                          </div>
                          {output.url ? (
                            <Image
                              src={output.url}
                              alt="生成结果"
                              width={768}
                              height={576}
                              className="mt-1.5 h-auto w-full rounded-md border border-slate-200 object-cover"
                              unoptimized
                            />
                          ) : null}
                          <button
                            type="button"
                            disabled={!output.downloadUrl}
                            onClick={() => {
                              if (!output.downloadUrl) return;
                              window.open(output.downloadUrl, "_blank", "noopener,noreferrer");
                            }}
                            className="mt-auto self-end pt-1.5 text-xs font-medium text-violet-600 hover:text-violet-700 disabled:cursor-not-allowed disabled:text-slate-400"
                          >
                            下载图片
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <div className="flex h-full min-h-[260px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-100/70 text-sm text-slate-500">
                输入需求开始创建图片对话任务。
              </div>
            )}
          </div>

          <div className="border-t border-slate-200/80 bg-white/75 backdrop-blur px-3 py-2 sm:px-4">
            <div className="relative">
              <textarea
                className="w-full resize-none rounded-3xl border border-slate-200 bg-slate-50 pl-3.5 pr-11 pt-2.5 pb-2.5 text-sm text-slate-700 outline-none ring-slate-200 placeholder:text-slate-400 shadow-[inset_0_1px_2px_rgba(15,23,42,0.04)] focus:bg-white focus:ring-2 focus:ring-violet-200"
                rows={2}
                value={draft.raw_request}
                onChange={(e) =>
                  setDraft((prev) => ({
                    ...prev,
                    raw_request: e.target.value,
                  }))
                }
                placeholder="输入原始需求，或继续补充修改..."
              />
              <button
                type="button"
                onClick={handleSubmitTask}
                disabled={!canSend}
                className={`absolute right-2 bottom-2 inline-flex h-8 w-8 items-center justify-center rounded-xl transition ${
                  canSend ? "bg-violet-600 hover:bg-violet-500" : "bg-slate-200"
                }`}
                aria-label={sending ? "处理中" : "发送并生成"}
              >
                {sending ? <LoadingIcon /> : <SendIcon disabled={!canSend} />}
              </button>
            </div>
            {optimizeError ? (
              <div className="mt-1.5 rounded-xl border border-rose-200/80 bg-rose-50/80 px-2.5 py-1.5 text-sm text-rose-600">
                {optimizeError}
              </div>
            ) : null}
          </div>
        </section>

        <aside className="order-3 flex min-h-0 flex-col rounded-2xl border border-slate-200/80 bg-white/70 shadow-[0_8px_24px_rgba(30,41,59,0.06)] backdrop-blur">
          <div className="flex items-center justify-between border-b border-slate-200/80 px-3 py-2">
            <span className="text-sm font-semibold text-slate-700">对话列表</span>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700 transition hover:bg-violet-100"
              onClick={handleNewConversation}
              aria-label="新建对话"
            >
              +新对话
            </button>
          </div>
          <div className="flex-1 space-y-1 overflow-y-auto p-1.5">
            {conversations.map((conversation) => (
              <button
                key={conversation.conversation_id}
                type="button"
                onClick={() => setActiveConversationId(conversation.conversation_id)}
                className={`w-full rounded-lg border px-2 py-1 text-left transition ${
                  activeConversationId === conversation.conversation_id
                    ? "border-violet-300 bg-violet-50/90 text-violet-800 shadow-[0_4px_12px_rgba(124,58,237,0.15)]"
                    : "border-slate-200/90 bg-white/80 text-slate-700 hover:bg-slate-100/70"
                }`}
              >
                <div className="truncate text-sm font-medium leading-5">{conversation.title}</div>
                <div
                  className={`mt-0.5 truncate text-[10px] ${
                    activeConversationId === conversation.conversation_id ? "text-violet-400/90" : "text-slate-400/80"
                  }`}
                >
                  {new Date(conversation.updated_at).toLocaleString()}
                </div>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </main>
  );
}
