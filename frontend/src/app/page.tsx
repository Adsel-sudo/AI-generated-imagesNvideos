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

    try {
      const optimizeRes = await optimizePrompt(
        buildOptimizePayload({
          draft: currentDraft,
          session_id: sessionId,
          conversation_id: selectedConversationId,
        }),
      );

      const optimized = optimizeRes.optimized_prompt_cn?.trim();
      optimizedPromptCn = optimized || undefined;
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
          session_id: sessionId,
          conversation_id: selectedConversationId,
          optimized_prompt_cn: optimizedPromptCn,
        }),
      );

      const taskId = generateRes.task_id || generateRes.task?.id;
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

  return (
    <main className="min-h-dvh bg-gradient-to-b from-slate-50 via-slate-50 to-slate-100/70 p-4 sm:p-6">
      <div className="mx-auto grid w-full max-w-7xl gap-4 lg:grid-cols-[280px_1fr]">
        <aside className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/70">
          <button
            type="button"
            className="inline-flex w-full items-center justify-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800"
            onClick={handleNewConversation}
          >
            + 新建对话
          </button>

          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-[11px] text-slate-500">
            session_id: <span className="font-medium text-slate-700">{sessionId || "初始化中..."}</span>
          </div>

          <div className="mt-4 space-y-2">
            {conversations.map((conversation) => (
              <button
                key={conversation.conversation_id}
                type="button"
                onClick={() => setActiveConversationId(conversation.conversation_id)}
                className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                  activeConversationId === conversation.conversation_id
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                <div className="truncate text-sm font-medium">{conversation.title}</div>
                <div
                  className={`mt-1 truncate text-xs ${
                    activeConversationId === conversation.conversation_id
                      ? "text-slate-200"
                      : "text-slate-400"
                  }`}
                >
                  conversation_id: {conversation.conversation_id}
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="flex min-h-[80dvh] flex-col rounded-2xl border border-slate-200/70 bg-white/80 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/70">
          <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
            {activeConversation?.messages.length ? (
              activeConversation.messages.map((message) => (
                <article
                  key={message.id}
                  className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="rounded-xl bg-slate-900/95 px-4 py-3 text-sm text-white">
                    <div className="mb-1 text-xs text-slate-300">用户输入</div>
                    {message.user_input}
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs text-slate-500">系统状态</span>
                      {message.system_status === "processing" ? (
                        <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                          处理中
                        </span>
                      ) : message.system_status === "done" ? (
                        <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                          已完成
                        </span>
                      ) : (
                        <span className="rounded-md bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700">
                          失败
                        </span>
                      )}
                    </div>

                    <div className="text-xs text-slate-500">尺寸：{message.size_text || "（未填写）"}</div>
                    <div className="text-xs text-slate-500">
                      风格倾向：{message.style_preference || "（未填写）"}
                    </div>
                    {message.error_message ? (
                      <div className="mt-2 text-xs text-rose-600">{message.error_message}</div>
                    ) : null}

                    {message.optimized_prompt ? (
                      <details className="mt-2 rounded-lg border border-slate-200 bg-white px-2 py-1">
                        <summary className="cursor-pointer text-xs font-medium text-slate-600">
                          查看优化后的提示词
                        </summary>
                        <div className="mt-1 text-xs text-slate-500">{message.optimized_prompt}</div>
                      </details>
                    ) : null}
                  </div>

                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-3">
                    <div className="text-xs text-slate-500">图片结果占位</div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      {message.generated_outputs.map((output) => (
                        <div
                          key={output.id}
                          className="rounded-lg border border-dashed border-slate-300 bg-white p-2"
                        >
                          <div className="aspect-[4/3] w-full rounded-md border border-dashed border-slate-300 bg-slate-50" />
                          <div className="mt-2 text-[11px] text-slate-500">
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
                              className="mt-2 h-auto w-full rounded-md border border-slate-200 object-cover"
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
                            className="mt-2 inline-flex items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
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
              <div className="flex h-full min-h-[340px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 text-sm text-slate-500">
                开始输入需求，创建第一轮对话式生图任务。
              </div>
            )}
          </div>

          <div className="border-t border-slate-200/80 bg-white/70 p-4 sm:p-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                  原始需求
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                    必填
                  </span>
                </div>
                <textarea
                  className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-4 focus:ring-slate-200"
                  rows={5}
                  value={draft.raw_request}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      raw_request: e.target.value,
                    }))
                  }
                  placeholder="请输入你的生图需求，例如：夏日海边防晒喷雾电商主图..."
                />
              </div>

              <div className="space-y-4">
                <div>
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                    尺寸选择
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                      选填
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm text-slate-700">
                    {[
                      { label: "1600 × 1600", value: "1600x1600" as const },
                      { label: "1464 × 600", value: "1464x600" as const },
                      { label: "600 × 450", value: "600x450" as const },
                      { label: "其他", value: "other" as const },
                    ].map((option) => (
                      <label
                        key={option.value}
                        className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5"
                      >
                        <input
                          type="radio"
                          name="size"
                          className="h-4 w-4 border-slate-300 text-slate-900 focus:ring-slate-400"
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
                      className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-4 focus:ring-slate-200"
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
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                    风格倾向
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                      选填
                    </span>
                  </div>
                  <input
                    className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-4 focus:ring-slate-200"
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
              </div>
            </div>

            <div className="mt-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                参考图片
                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                  选填
                </span>
              </div>
              <div className="mb-2 text-xs text-slate-500">
                商品图已上传 {draft.references.product.length} 张
                {draft.preserve_product_fidelity ? "（已启用商品一致性）" : ""}
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  { label: "商品图", key: "product" },
                  { label: "元素/构图参考图", key: "composition" },
                  { label: "姿势参考图", key: "pose" },
                  { label: "风格参考图", key: "style" },
                ].map((item) => {
                  const category = item.key as ReferenceCategory;
                  return (
                  <div
                    key={item.key}
                    className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-3"
                  >
                    <div className="text-xs font-medium text-slate-900">{item.label}</div>
                    <div className="mt-1 text-[11px] text-slate-500">支持多图上传、预览与删除</div>
                    <label className="mt-2 inline-flex cursor-pointer items-center rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 hover:bg-slate-50">
                      {uploadingMap[category] ? "上传中..." : "上传图片"}
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
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        {draft.references[category].map((asset) => (
                          <div key={asset.local_id} className="rounded-lg border border-slate-200 bg-white p-1">
                            <Image
                              src={asset.preview_url}
                              alt={asset.file_name || "参考图"}
                              width={160}
                              height={120}
                              className="h-16 w-full rounded object-cover"
                              unoptimized
                            />
                            <button
                              type="button"
                              className="mt-1 w-full rounded border border-rose-200 px-1 py-0.5 text-[10px] text-rose-600 hover:bg-rose-50"
                              onClick={() => handleRemoveReference(category, asset.local_id)}
                            >
                              删除
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-2 h-14 rounded-lg border border-dashed border-slate-200 bg-white/80" />
                    )}
                  </div>
                  );
                })}
              </div>
            </div>

            {optimizeError ? (
              <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {optimizeError}
              </div>
            ) : null}

            <div className="mt-4 flex justify-end">
              <button
                type="button"
                className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-slate-200 disabled:cursor-not-allowed disabled:bg-slate-600"
                onClick={handleSubmitTask}
                disabled={isSubmitting || optimizeLoading}
              >
                {optimizeLoading ? "正在整理需求..." : isSubmitting ? "任务提交中..." : "发送并生成"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
