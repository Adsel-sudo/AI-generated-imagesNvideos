"use client";

import { type SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { getApiBaseUrl } from "@/src/lib/api/client";
import {
  cancelTask,
  generateImageTask,
  getOutputDownloadUrl,
  getTaskOutputs,
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
  resolveDraftSize,
} from "@/src/lib/conversation/payload";
import { getFriendlyErrorMessage } from "@/src/lib/error-mapping";
import type { Conversation } from "@/src/types/conversation";
import {
  createEmptyWorkbenchDraft,
  type ReferenceCategory,
  type ResolutionOption,
  type WorkbenchDraft,
} from "@/src/types/workbench";
import type { GeneratedOutput } from "@/src/types/conversation";
import { SessionSidebar } from "@/src/components/workbench/SessionSidebar";
import { LoginModal } from "@/src/components/auth/LoginModal";
import { useTaskPolling } from "@/src/hooks/useTaskPolling";
import { useAuthStatus } from "@/src/hooks/useAuthStatus";

type SizeOption = "1:1" | "16:9" | "4:3" | "3:2" | "other";

const PRESET_SIZES = ["1:1", "16:9", "4:3", "3:2"] as const;
const RESOLUTION_OPTIONS: ResolutionOption[] = ["2K", "4K"];
const REFERENCE_LIMITS: Record<ReferenceCategory, number> = {
  product: 3,
  composition: 2,
  pose: 2,
  style: 2,
};
const TOTAL_REFERENCE_LIMIT = 8;
const REFERENCE_GROUPS: Array<{ label: string; key: ReferenceCategory; limit: number }> = [
  { label: "商品图", key: "product", limit: REFERENCE_LIMITS.product },
  { label: "元素/构图参考图", key: "composition", limit: REFERENCE_LIMITS.composition },
  { label: "姿势参考图", key: "pose", limit: REFERENCE_LIMITS.pose },
  { label: "风格参考图", key: "style", limit: REFERENCE_LIMITS.style },
];
const PANEL_SECTION_SPACING = "py-3";
const OPTIONAL_BADGE_CLASS =
  "inline-flex items-center rounded-full border border-violet-200/70 bg-violet-50/70 px-1.5 py-0.5 text-[10px] font-medium leading-none text-violet-500";
const TASK_OUTPUTS_PAGE_SIZE = 30;

const getSizeDisplayText = (size: string) => {
  if (size === "1:1") return "方图（1:1）";
  if (size === "16:9") return "横图（16:9）";
  if (size === "4:3") return "标准横图（4:3）";
  if (size === "3:2") return "横图（3:2）";
  return size.trim() || "（未填写）";
};

const ASPECT_RATIO_PATTERN = /^([1-9]\d*):([1-9]\d*)$/;

const sanitizeAspectRatioInput = (value: string) => {
  const normalized = value
    .replace(/：/g, ":")
    .replace(/\s+/g, "")
    .replace(/[０-９]/g, (char) => String(char.charCodeAt(0) - 0xff10));

  let result = "";
  let hasColon = false;

  for (const char of normalized) {
    if (/\d/.test(char)) {
      result += char;
      continue;
    }
    if (char === ":" && !hasColon && result.length > 0) {
      result += ":";
      hasColon = true;
    }
  }

  return result;
};

const mapTaskOutputsToGeneratedOutputs = (
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
) =>
  outputs?.map((output) => {
    const originalUrl = output.original_url || getOutputDownloadUrl(taskId, output.id);
    const downloadUrl = getOutputDownloadUrl(taskId, output.id, { download: true });
    const thumbnailUrl = output.thumbnail_url || output.preview_url || output.lowres_url || undefined;
    const modalPreviewUrl = output.preview_url || thumbnailUrl;
    return {
      id: output.id,
      kind: "image" as const,
      url: originalUrl || modalPreviewUrl,
      preview_url: thumbnailUrl,
      modal_preview_url: modalPreviewUrl,
      downloadUrl,
      file_path: output.file_path || undefined,
      file_name: output.file_name || undefined,
      status: "ready" as const,
    };
  }) ?? [];

const resolveStablePreviewUrl = (params: {
  fileId?: string;
  filePath?: string;
  backendUrl?: string;
  fallbackObjectUrl?: string;
}) => {
  if (params.backendUrl) {
    if (/^https?:\/\//i.test(params.backendUrl)) {
      return params.backendUrl;
    }
    return `${getApiBaseUrl()}${params.backendUrl.startsWith("/") ? "" : "/"}${params.backendUrl}`;
  }

  if (params.fileId) {
    return `${getApiBaseUrl()}/api/files/${params.fileId}`;
  }

  if (params.filePath) {
    const normalized = params.filePath.replace(/\\/g, "/");
    const filename = normalized.split("/").pop() || "";
    const extIndex = filename.lastIndexOf(".");
    const fileIdFromPath = extIndex > 0 ? filename.slice(0, extIndex) : filename;
    if (fileIdFromPath) {
      return `${getApiBaseUrl()}/api/files/${fileIdFromPath}`;
    }
  }

  return params.fallbackObjectUrl || "";
};

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
    return "bg-emerald-100/90 text-emerald-700";
  }
  if (status === "cancelled") {
    return "bg-slate-200/80 text-slate-700";
  }
  if (status === "error") {
    return "bg-rose-100/90 text-rose-700";
  }
  return "bg-amber-100/90 text-amber-700";
}

const triggerImageDownload = (downloadUrl: string, fileName?: string) => {
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = fileName || "";
  link.rel = "noopener noreferrer";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

export default function ImageWorkbenchPage() {
  const {
    loading: authLoading,
    isAuthenticated,
    loginWithPassword,
  } = useAuthStatus();
  const [sessionId, setSessionId] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>("");
  const [draftByConversationId, setDraftByConversationId] = useState<Record<string, WorkbenchDraft>>({});

  const [draft, setDraft] = useState<WorkbenchDraft>(createEmptyWorkbenchDraft());

  const [optimizeLoading, setOptimizeLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [previewState, setPreviewState] = useState<{
    outputs: GeneratedOutput[];
    activeIndex: number;
  } | null>(null);
  const [openOptimizedPromptMessageId, setOpenOptimizedPromptMessageId] = useState<string | null>(null);
  const [, setOptimizeError] = useState<string | null>(null);
  const [referenceError, setReferenceError] = useState<string | null>(null);
  const [uploadingMap, setUploadingMap] = useState<Record<ReferenceCategory, boolean>>({
    product: false,
    composition: false,
    pose: false,
    style: false,
  });
  const conversationEndRef = useRef<HTMLDivElement | null>(null);
  const currentMessageRef = useRef<HTMLElement | null>(null);
  const promptInputRef = useRef<HTMLTextAreaElement | null>(null);
  const optimizedPromptPopoverRef = useRef<HTMLDivElement | null>(null);
  const totalReferenceCount = useMemo(
    () =>
      Object.values(draft.references).reduce((sum, assets) => {
        return sum + assets.length;
      }, 0),
    [draft.references],
  );

  const selectedSizeOption: SizeOption = useMemo(() => {
    if (draft.sizeMode === "custom") {
      return "other";
    }
    if (PRESET_SIZES.includes(draft.presetSize as (typeof PRESET_SIZES)[number])) {
      return draft.presetSize as SizeOption;
    }
    return "1:1";
  }, [draft.presetSize, draft.sizeMode]);

  const customSizeReady = ASPECT_RATIO_PATTERN.test(draft.customAspectRatio);
  const selectedResolution: ResolutionOption = useMemo(
    () => (RESOLUTION_OPTIONS.includes(draft.resolution) ? draft.resolution : "2K"),
    [draft.resolution],
  );
  const previewOutput = useMemo(() => {
    if (!previewState) return null;
    return previewState.outputs[previewState.activeIndex] ?? null;
  }, [previewState]);
  const [previewImageSrc, setPreviewImageSrc] = useState<string | null>(null);
  const previewHasMultiple = (previewState?.outputs.length || 0) > 1;

  useEffect(() => {
    if (!previewOutput) {
      setPreviewImageSrc(null);
      return;
    }

    const fallbackSrc = previewOutput.modal_preview_url || previewOutput.preview_url || previewOutput.url || null;
    const originalSrc = previewOutput.url || null;
    setPreviewImageSrc(fallbackSrc);

    if (!originalSrc || originalSrc === fallbackSrc) {
      return;
    }

    const preloader = new window.Image();
    preloader.src = originalSrc;
    preloader.onload = () => {
      setPreviewImageSrc(originalSrc);
    };
  }, [previewOutput]);

  useEffect(() => {
    if (!openOptimizedPromptMessageId) return;

    const handlePointerDownOutside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!optimizedPromptPopoverRef.current?.contains(target)) {
        setOpenOptimizedPromptMessageId(null);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenOptimizedPromptMessageId(null);
      }
    };

    window.addEventListener("pointerdown", handlePointerDownOutside);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDownOutside);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [openOptimizedPromptMessageId]);

  useEffect(() => {
    setOpenOptimizedPromptMessageId(null);
  }, [activeConversationId]);

  const handleOpenPreview = (outputs: GeneratedOutput[], activeIndex: number) => {
    if (!outputs.length) return;
    const normalizedIndex = Math.max(0, Math.min(activeIndex, outputs.length - 1));
    setPreviewState({
      outputs,
      activeIndex: normalizedIndex,
    });
  };

  const getPreviewableOutputs = (outputs: GeneratedOutput[]) =>
    outputs
      .filter((item) => Boolean(item.downloadUrl || item.url) && item.status === "ready")
      .map((item) => ({
        ...item,
        url: item.url || item.downloadUrl,
      }));

  const handleOpenPreviewById = (outputs: GeneratedOutput[], outputId: string) => {
    const previewableOutputs = getPreviewableOutputs(outputs);
    if (!previewableOutputs.length) return;
    const activeIndex = Math.max(
      0,
      previewableOutputs.findIndex((item) => item.id === outputId),
    );
    handleOpenPreview(previewableOutputs, activeIndex);
  };

  const handleClosePreview = useCallback(() => {
    setPreviewState(null);
  }, []);

  const handlePreviewPrev = useCallback(() => {
    setPreviewState((prev) => {
      if (!prev || prev.outputs.length <= 1) return prev;
      const nextIndex = (prev.activeIndex - 1 + prev.outputs.length) % prev.outputs.length;
      return {
        ...prev,
        activeIndex: nextIndex,
      };
    });
  }, []);

  const handlePreviewNext = useCallback(() => {
    setPreviewState((prev) => {
      if (!prev || prev.outputs.length <= 1) return prev;
      const nextIndex = (prev.activeIndex + 1) % prev.outputs.length;
      return {
        ...prev,
        activeIndex: nextIndex,
      };
    });
  }, []);

  const activeConversation = useMemo(
    () => conversations.find((item) => item.conversation_id === activeConversationId) ?? null,
    [activeConversationId, conversations],
  );
  const hasMessages = Boolean(activeConversation?.messages.length);
  const activeConversationStatusSignature = useMemo(
    () =>
      activeConversation?.messages
        .map((message) => `${message.id}:${message.system_status}:${message.generated_outputs.map((output) => output.status).join(",")}`)
        .join("|") ?? "",
    [activeConversation],
  );

  const scrollToConversationBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    conversationEndRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  const scrollToCurrentMessage = useCallback(
    (behavior: ScrollBehavior = "smooth") => {
      if (currentMessageRef.current) {
        currentMessageRef.current.scrollIntoView({ behavior, block: "nearest" });
        return;
      }
      scrollToConversationBottom(behavior);
    },
    [scrollToConversationBottom],
  );

  useEffect(() => {
    const state = loadConversationState();
    setSessionId(state.session_id);
    setConversations(state.conversations);
    setActiveConversationId(state.active_conversation_id);
    setDraftByConversationId(state.draft_by_conversation_id);

    const initialDraft =
      (state.active_conversation_id && state.draft_by_conversation_id[state.active_conversation_id]) ||
      createEmptyWorkbenchDraft();
    setDraft(initialDraft);
  }, []);

  useEffect(() => {
    if (!sessionId || !activeConversationId || !conversations.length) return;
    persistConversationState({
      session_id: sessionId,
      active_conversation_id: activeConversationId,
      conversations,
      draft_by_conversation_id: draftByConversationId,
    });
  }, [activeConversationId, conversations, draftByConversationId, sessionId]);

  useEffect(() => {
    if (!activeConversationId) return;

    const existingDraft = draftByConversationId[activeConversationId];
    if (existingDraft) {
      setDraft(existingDraft);
      setOptimizeError(null);
      setReferenceError(null);
      return;
    }

    const emptyDraft = createEmptyWorkbenchDraft();
    const nextDraft: WorkbenchDraft = {
      ...emptyDraft,
      reserved: {
        ...emptyDraft.reserved,
        session_id: sessionId,
        conversation_id: activeConversationId,
      },
    };

    setDraft(nextDraft);
    setDraftByConversationId((prev) => ({
      ...prev,
      [activeConversationId]: nextDraft,
    }));
    setOptimizeError(null);
    setReferenceError(null);
  }, [activeConversationId, draftByConversationId, sessionId]);

  useEffect(() => {
    if (!activeConversationId) return;
    scrollToConversationBottom("smooth");
  }, [activeConversationId, scrollToConversationBottom]);

  useEffect(() => {
    if (!activeConversationId) return;
    scrollToConversationBottom("smooth");
  }, [activeConversation?.messages.length, activeConversationId, scrollToConversationBottom]);

  useEffect(() => {
    if (!previewState) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        handleClosePreview();
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        handlePreviewPrev();
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        handlePreviewNext();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleClosePreview, handlePreviewNext, handlePreviewPrev, previewState]);

  useEffect(() => {
    if (!activeConversationId || !activeConversationStatusSignature) return;
    scrollToCurrentMessage("smooth");
  }, [activeConversationId, activeConversationStatusSignature, scrollToCurrentMessage]);

  const setActiveDraft = (updater: SetStateAction<WorkbenchDraft>) => {
    setDraft((prev) => {
      const nextDraft =
        typeof updater === "function" ? (updater as (prevState: WorkbenchDraft) => WorkbenchDraft)(prev) : updater;

      if (activeConversationId) {
        setDraftByConversationId((prevDrafts) => ({
          ...prevDrafts,
          [activeConversationId]: nextDraft,
        }));
      }

      return nextDraft;
    });
  };

  const createConversationDraft = (conversationId: string): WorkbenchDraft => {
    const emptyDraft = createEmptyWorkbenchDraft();
    return {
      ...emptyDraft,
      reserved: {
        ...emptyDraft.reserved,
        session_id: sessionId,
        conversation_id: conversationId,
      },
    };
  };

  const handleNewConversation = () => {
    const conversation = createConversation();
    const nextDraft = createConversationDraft(conversation.conversation_id);

    setConversations((prev) => [conversation, ...prev]);
    setDraft(nextDraft);
    setDraftByConversationId((prev) => ({
      ...prev,
      [conversation.conversation_id]: nextDraft,
    }));
    setOptimizeError(null);
    setReferenceError(null);
    setActiveConversationId(conversation.conversation_id);
  };

  const handleDeleteConversation = (conversationId: string) => {
    setConversations((prev) => {
      const targetIndex = prev.findIndex((item) => item.conversation_id === conversationId);
      if (targetIndex === -1) return prev;

      let nextConversations = prev.filter((item) => item.conversation_id !== conversationId);
      let nextActiveId = activeConversationId;

      if (nextConversations.length === 0) {
        const fallbackConversation = createConversation();
        const fallbackDraft = createConversationDraft(fallbackConversation.conversation_id);
        nextConversations = [fallbackConversation];
        nextActiveId = fallbackConversation.conversation_id;
        setDraft(fallbackDraft);
        setDraftByConversationId({ [fallbackConversation.conversation_id]: fallbackDraft });
      } else {
        setDraftByConversationId((prevDrafts) => {
          const nextDrafts = { ...prevDrafts };
          delete nextDrafts[conversationId];
          return nextDrafts;
        });

        if (activeConversationId === conversationId) {
          const fallbackConversation =
            nextConversations[targetIndex] ?? nextConversations[targetIndex - 1] ?? nextConversations[0];
          nextActiveId = fallbackConversation.conversation_id;
        }
      }

      setActiveConversationId(nextActiveId);
      setOptimizeError(null);
      setReferenceError(null);

      return nextConversations;
    });
  };

  const updatePreserveProductFidelity = (nextDraft: WorkbenchDraft): WorkbenchDraft => ({
    ...nextDraft,
    preserve_product_fidelity: nextDraft.references.product.length > 0,
  });

  const handleUploadFiles = async (category: ReferenceCategory, files: FileList | null) => {
    if (!files?.length) return;

    const categoryLimit = REFERENCE_LIMITS[category];
    const currentCategoryCount = draft.references[category].length;
    const categoryRemaining = Math.max(0, categoryLimit - currentCategoryCount);
    const totalRemaining = Math.max(0, TOTAL_REFERENCE_LIMIT - totalReferenceCount);

    if (categoryRemaining <= 0) {
      setReferenceError(`「${REFERENCE_GROUPS.find((item) => item.key === category)?.label || "当前分组"}」最多上传 ${categoryLimit} 张`);
      return;
    }
    if (totalRemaining <= 0) {
      setReferenceError(`参考图片总数最多 ${TOTAL_REFERENCE_LIMIT} 张`);
      return;
    }

    const allowedCount = Math.min(files.length, categoryRemaining, totalRemaining);
    const selectedFiles = Array.from(files).slice(0, allowedCount);

    if (allowedCount < files.length) {
      setReferenceError(`已超出数量限制，本次仅上传前 ${allowedCount} 张`);
    } else {
      setReferenceError(null);
    }

    setUploadingMap((prev) => ({ ...prev, [category]: true }));

    try {
      const uploadedAssets = await Promise.all(
        selectedFiles.map(async (file) => {
          const uploaded = await uploadFile(file);
          return {
            local_id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
            file_id: uploaded.file_id,
            file_path: uploaded.file_path || "",
            file_name: uploaded.file_name || file.name,
            mime_type: uploaded.mime_type || file.type,
            preview_url: resolveStablePreviewUrl({
              fileId: uploaded.file_id,
              filePath: uploaded.file_path,
              backendUrl: uploaded.url,
              fallbackObjectUrl: URL.createObjectURL(file),
            }),
          };
        }),
      );

      setActiveDraft((prev) =>
        updatePreserveProductFidelity({
          ...prev,
          references: {
            ...prev.references,
            [category]: [...prev.references[category], ...uploadedAssets],
          },
        }),
      );
    } catch (error) {
      setReferenceError(getFriendlyErrorMessage("upload_failed", error));
    } finally {
      setUploadingMap((prev) => ({ ...prev, [category]: false }));
    }
  };

  const handleDropFiles = (category: ReferenceCategory, files: FileList | null) => {
    if (!files?.length) return;
    void handleUploadFiles(category, files);
  };

  const handleRemoveReference = (category: ReferenceCategory, localId: string) => {
    setActiveDraft((prev) => {
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

  const handleModifyGeneratedImage = (output: {
    id: string;
    file_path?: string;
    file_name?: string;
    url?: string;
    downloadUrl?: string;
  }) => {
    if (!output.file_path) {
      setReferenceError("当前图片暂不支持继续修改，请重新生成后再试。");
      return;
    }

    const filePath = output.file_path;
    const fileName = output.file_name || `output_${output.id}.png`;
    const previewUrl = output.url || output.downloadUrl || "";

    setReferenceError(null);
    setOptimizeError(null);
    setOptimizeLoading(false);
    setIsSubmitting(false);
    setActiveDraft((prev) =>
      updatePreserveProductFidelity({
        ...prev,
        references: {
          ...prev.references,
          composition: [
            {
              local_id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
              file_id: output.id,
              file_path: filePath,
              file_name: fileName,
              mime_type: "image/png",
              preview_url: previewUrl,
            },
            ...prev.references.composition,
          ].slice(0, REFERENCE_LIMITS.composition),
        },
      }),
    );
    requestAnimationFrame(() => {
      promptInputRef.current?.focus();
    });
  };

  const updateMessageById = useCallback((
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
  }, []);

  const { startPollingTask } = useTaskPolling({
    conversations,
    updateMessageById,
    mapTaskOutputsToGeneratedOutputs,
  });

  const handleCancelTask = useCallback(
    async ({ conversationId, messageId, taskId }: { conversationId: string; messageId: string; taskId: string }) => {
      try {
        const task = await cancelTask(taskId);
        const outputRes = task.output_count
          ? await getTaskOutputs(taskId, { page: 1, page_size: TASK_OUTPUTS_PAGE_SIZE })
          : null;
        const outputs = mapTaskOutputsToGeneratedOutputs(taskId, outputRes?.items);
        updateMessageById(conversationId, messageId, (message) => ({
          ...message,
          system_status: "cancelled",
          progress_current: task.progress_current ?? message.progress_current,
          progress_total: task.progress_total ?? message.progress_total,
          progress_message: task.message || "已停止",
          generated_outputs: outputs.length ? outputs : message.generated_outputs,
        }));
      } catch (error) {
        updateMessageById(conversationId, messageId, (message) => ({
          ...message,
          error_message: getFriendlyErrorMessage("submit_failed", error),
        }));
      }
    },
    [updateMessageById],
  );

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

    const latestDraftFromStore =
      (selectedConversationId && draftByConversationId[selectedConversationId]) || undefined;
    const baseDraft = latestDraftFromStore || draft;
    const currentDraft: WorkbenchDraft = {
      ...baseDraft,
      reserved: {
        ...baseDraft.reserved,
        session_id: sessionId,
        conversation_id: selectedConversationId,
      },
    };
    setDraftByConversationId((prev) => ({
      ...prev,
      [selectedConversationId]: currentDraft,
    }));
    if (selectedConversationId === activeConversationId) {
      setDraft(currentDraft);
    }

    setOptimizeError(null);
    setReferenceError(null);
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
      optimized_prompt: optimizedPromptCn || currentDraft.raw_request.trim(),
      size_text: getSizeDisplayText(resolveDraftSize(currentDraft)),
      style_preference: currentDraft.style_preference.trim() || undefined,
      progress_current: 0,
      progress_total: 2,
      progress_message: "生成中 0/2",
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

      startPollingTask({
        conversationId: selectedConversationId,
        messageId: message.id,
        taskId,
      });
      setActiveDraft((prev) => ({ ...prev, raw_request: "" }));
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

  const handleLogin = async ({ username, password }: { username: string; password: string }) => {
    await loginWithPassword(username, password);
  };


  const sending = optimizeLoading || isSubmitting;
  const hasValidSize = selectedSizeOption !== "other" || customSizeReady;
  const canSend = isAuthenticated && draft.raw_request.trim().length > 0 && !sending && hasValidSize;

  return (
    <main className="relative h-[calc(100dvh-60px)] overflow-hidden bg-slate-100/80 px-2.5 py-1.5 sm:px-3 sm:py-2">
      <div className={`mx-auto grid h-full w-full max-w-[1480px] grid-cols-1 gap-1.5 lg:grid-cols-[304px_minmax(0,1fr)_280px] lg:gap-x-2.5 ${!isAuthenticated ? "pointer-events-none select-none opacity-70" : ""}`}>
        <aside className="order-2 flex min-h-0 flex-col rounded-2xl border border-slate-200/80 bg-white/70 shadow-[0_8px_24px_rgba(30,41,59,0.06)] backdrop-blur lg:order-1">
          <div className="flex-1 overflow-y-auto px-3 pt-6 pb-2 sm:px-4">
            <div className="divide-y divide-slate-200/80">
              <div className={`${PANEL_SECTION_SPACING} pt-0`}>
                <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                  <span>比例选择</span>
                  <span className={OPTIONAL_BADGE_CLASS}>选填</span>
                </div>
                <div className="grid grid-cols-1 gap-1.5 text-sm text-slate-700">
                  {[
                    { label: "方图（1:1）", value: "1:1" as const },
                    { label: "横图（16:9）", value: "16:9" as const },
                    { label: "标准横图（4:3）", value: "4:3" as const },
                    { label: "横图（3:2）", value: "3:2" as const },
                    { label: "其他", value: "other" as const },
                  ].map((option) => (
                    <label
                      key={option.value}
                      className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-slate-100/70 px-2.5 py-1.5"
                    >
                      <input
                        type="radio"
                        name="size"
                        className="h-4 w-4 border-slate-300 text-violet-600 focus:ring-violet-300"
                        checked={selectedSizeOption === option.value}
                        onChange={() => {
                          if (option.value === "other") {
                            setActiveDraft((prev) => ({
                              ...prev,
                              sizeMode: "custom",
                            }));
                            return;
                          }
                          setActiveDraft((prev) => ({
                            ...prev,
                            sizeMode: "preset",
                            presetSize: option.value,
                          }));
                        }}
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
                {selectedSizeOption === "other" ? (
                  <div className="mt-1.5 space-y-1.5">
                    <input
                      className="w-full rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-violet-200"
                      placeholder="请输入比例，例如 21:9"
                      value={draft.customAspectRatio}
                      onChange={(e) => {
                        const nextAspectRatio = sanitizeAspectRatioInput(e.target.value);
                        setActiveDraft((prev) => ({
                          ...prev,
                          sizeMode: "custom",
                          customAspectRatio: nextAspectRatio,
                        }));
                      }}
                    />
                    {draft.customAspectRatio && !customSizeReady ? (
                      <div className="text-xs text-amber-600">比例格式应为 正整数:正整数，例如 21:9</div>
                    ) : null}
                  </div>
                ) : null}
                <div className="mt-2 text-xs text-slate-500">
                  实际输出分辨率由模型决定，系统将尽量匹配所选比例
                </div>
              </div>

              <div className={PANEL_SECTION_SPACING}>
                <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                  <span>分辨率</span>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {RESOLUTION_OPTIONS.map((option) => {
                    const selected = selectedResolution === option;
                    return (
                      <button
                        key={option}
                        type="button"
                        onClick={() =>
                          setActiveDraft((prev) => ({
                            ...prev,
                            resolution: option,
                          }))
                        }
                        className={`rounded-lg border px-2.5 py-2 text-sm font-medium transition ${
                          selected
                            ? "border-violet-300 bg-violet-50 text-violet-700"
                            : "border-slate-200 bg-slate-100/70 text-slate-700 hover:border-violet-200 hover:text-violet-600"
                        }`}
                        aria-pressed={selected}
                      >
                        {option}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className={PANEL_SECTION_SPACING}>
                <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                  <span>风格需求</span>
                  <span className={OPTIONAL_BADGE_CLASS}>选填</span>
                </div>
                <input
                  className="w-full rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-violet-200"
                  placeholder="例：清爽、明亮、度假感、夏日氛围"
                  value={draft.style_preference}
                  onChange={(e) =>
                    setActiveDraft((prev) => ({
                      ...prev,
                      style_preference: e.target.value,
                    }))
                  }
                />
              </div>

              <div className={`${PANEL_SECTION_SPACING} pb-0`}>
                <div className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                  <span>参考图片</span>
                  <span className={OPTIONAL_BADGE_CLASS}>选填</span>
                </div>
                <div className="mb-2.5 text-xs text-slate-500">
                  总数最多 {TOTAL_REFERENCE_LIMIT} 张（当前 {totalReferenceCount}/{TOTAL_REFERENCE_LIMIT}）
                </div>
                {referenceError ? (
                  <div className="mb-2 rounded-xl border border-rose-200/80 bg-rose-50/80 px-2.5 py-1.5 text-sm text-rose-600">
                    {referenceError}
                  </div>
                ) : null}
                <div className="space-y-2.5">
                  {REFERENCE_GROUPS.map((item) => {
                    const category = item.key;
                    return (
                      <div key={item.key} className="space-y-1.5 rounded-xl border border-slate-200/80 bg-slate-50/50 p-2">
                        <div className="text-xs font-medium text-slate-700">
                          {item.label}（最多{item.limit}张）
                        </div>
                        <label
                          className="block cursor-pointer rounded-lg border border-dashed border-slate-300 bg-white px-2 py-2 text-center text-xs text-slate-500 transition hover:border-violet-300 hover:text-violet-600"
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
                          <div className="grid grid-cols-4 gap-1.5">
                            {draft.references[category].map((asset) => (
                              <div key={asset.local_id} className="group relative h-[68px] w-[68px]">
                                <Image
                                  src={asset.preview_url}
                                  alt={asset.file_name || "参考图"}
                                  width={68}
                                  height={68}
                                  className="h-[68px] w-[68px] rounded-md border border-slate-200 bg-white object-cover"
                                  unoptimized
                                />
                                <button
                                  type="button"
                                  className="absolute right-0 top-0 inline-flex h-4 w-4 -translate-y-1/2 translate-x-1/2 items-center justify-center rounded-full bg-rose-500 text-[10px] text-white opacity-95 shadow-sm transition hover:bg-rose-600"
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
          </div>
        </aside>

        <section className="order-1 flex h-[calc(100%-5px)] min-h-0 flex-col rounded-2xl border border-slate-200/80 bg-white/70 shadow-[0_8px_24px_rgba(30,41,59,0.06)] backdrop-blur lg:order-2">
          <div
            className={`min-h-0 flex-1 px-3 pt-5 pb-2 sm:px-4 ${
              hasMessages ? "overflow-y-auto" : "overflow-y-hidden"
            }`}
          >
            {hasMessages ? (
              <div className="space-y-2.5 pb-1">
                {activeConversation?.messages.map((message, index) => (
                <article
                  key={message.id}
                  ref={index === activeConversation.messages.length - 1 ? currentMessageRef : null}
                  className="space-y-2"
                >
                  <div className="ml-auto max-w-[54%] rounded-2xl bg-violet-500/90 px-3 py-2 text-sm text-white shadow-sm">
                    {message.user_input}
                  </div>

                  <div className={`relative max-w-[78%] space-y-2 ${message.optimized_prompt ? "pt-6" : ""}`}>
                    {message.optimized_prompt ? (
                      <div
                        className="absolute top-0 left-0 z-20"
                        ref={(node) => {
                          if (openOptimizedPromptMessageId === message.id) {
                            optimizedPromptPopoverRef.current = node;
                          }
                        }}
                      >
                        <button
                          type="button"
                          className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-700"
                          onClick={() =>
                            setOpenOptimizedPromptMessageId((prev) => (prev === message.id ? null : message.id))
                          }
                        >
                          查看优化后的提示词
                        </button>
                        {openOptimizedPromptMessageId === message.id ? (
                          <div className="absolute top-7 left-0 w-[min(32rem,calc(100vw-7rem))] max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2.5 text-left text-xs text-slate-500 shadow-lg">
                            {message.optimized_prompt}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {message.system_status === "error" && message.error_message ? (
                      <div className="rounded-xl border border-rose-200 bg-rose-50/70 px-2.5 py-2">
                        <div className="truncate text-xs text-rose-600">{message.error_message}</div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <div className="inline-flex items-center gap-1.5">
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${getMessageStatusBadge(
                              message.system_status,
                            )}`}
                          >
                            {message.system_status === "done"
                              ? "生成完成"
                              : message.system_status === "cancelled"
                                ? "已停止"
                                : `生成中 ${Math.max(0, message.progress_current || 0)}/${Math.max(
                                    0,
                                    message.progress_total || 0,
                                  )}`}
                          </span>
                          {message.system_status === "processing" ? (
                            <span className="inline-flex h-4 w-4 items-center justify-center text-slate-400">
                              <LoadingIcon />
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2">
                          {message.system_status === "processing" && message.task_id ? (
                            <button
                              type="button"
                              className="inline-flex items-center rounded-md border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-600 transition hover:bg-rose-100"
                              onClick={() =>
                                handleCancelTask({
                                  conversationId: activeConversationId,
                                  messageId: message.id,
                                  taskId: message.task_id!,
                                })
                              }
                            >
                              停止生成
                            </button>
                          ) : null}
                        </div>
                      </div>
                    )}
                    {message.system_status === "processing" && message.generated_outputs.length === 0 ? (
                      <div className="rounded-xl border border-slate-200/80 bg-white/75 p-2">
                        <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                          {[0, 1, 2].map((placeholder) => (
                            <div
                              key={placeholder}
                              className="animate-pulse rounded-lg border border-slate-200 bg-white p-1.5"
                            >
                              <div className="aspect-[4/3] w-full rounded-md border border-slate-200 bg-slate-100/80" />
                              <div className="mt-1.5 h-2.5 w-2/3 rounded bg-slate-100" />
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                        {message.generated_outputs.map((output) => (
                          <div
                            key={output.id}
                            className="flex h-full flex-col rounded-lg border border-slate-200 bg-white p-1.5"
                          >
                            <div className="space-y-1.5">
                              {output.preview_url ? (
                                <button
                                  type="button"
                                  className="group relative block w-full overflow-hidden rounded-md border border-slate-200"
                                  onClick={() => handleOpenPreviewById(message.generated_outputs, output.id)}
                                  aria-label="查看原图"
                                >
                                  <div className="aspect-[4/3] w-full overflow-hidden">
                                    <Image
                                      src={output.preview_url}
                                      alt="生成结果预览"
                                      width={768}
                                      height={576}
                                      className="h-full w-full object-cover transition duration-200 group-hover:scale-[1.01]"
                                      unoptimized
                                    />
                                  </div>
                                </button>
                              ) : (
                                <div className="flex aspect-[4/3] w-full items-center justify-center rounded-md border border-slate-200 bg-slate-100/70 text-xs text-slate-500">
                                  仅展示预览信息
                                </div>
                              )}
                              <button
                                type="button"
                                className="text-xs font-medium text-slate-500 transition hover:text-slate-700"
                                onClick={() => handleOpenPreviewById(message.generated_outputs, output.id)}
                              >
                                查看原图
                              </button>
                            </div>
                            <div className="mt-auto flex items-center justify-end gap-2 pt-1.5">
                              <button
                                type="button"
                                disabled={!output.file_path}
                                onClick={() => handleModifyGeneratedImage(output)}
                                className="text-xs font-medium text-slate-600 hover:text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                              >
                                修改此图
                              </button>
                              <button
                                type="button"
                                disabled={!output.downloadUrl}
                                onClick={() => {
                                  if (!output.downloadUrl) return;
                                  triggerImageDownload(
                                    output.downloadUrl,
                                    output.file_name || `generated_${output.id}.png`,
                                  );
                                }}
                                className="text-xs font-medium text-violet-600 hover:text-violet-700 disabled:cursor-not-allowed disabled:text-slate-400"
                              >
                                下载图片
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </article>
                ))}
              </div>
            ) : (
              <div className="flex min-h-[220px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-100/70 px-4 text-sm text-slate-500">
                输入需求开始创建图片对话任务。
              </div>
            )}
            <div ref={conversationEndRef} />
          </div>

          <div className="mt-1.5 px-[7px] pb-[1px] pt-1.5 sm:px-[11px]">
            <div className="relative">
              <textarea
                ref={promptInputRef}
                className="w-full resize-none rounded-2xl border border-slate-200 bg-white pl-3.5 pr-11 pt-2.5 pb-2.5 text-sm text-slate-700 outline-none ring-slate-200 placeholder:text-slate-400 shadow-[inset_0_1px_2px_rgba(15,23,42,0.04)] focus:bg-white focus:ring-2 focus:ring-violet-200"
                rows={2}
                value={draft.raw_request}
                onChange={(e) =>
                  setActiveDraft((prev) => ({
                    ...prev,
                    raw_request: e.target.value,
                  }))
                }
                placeholder="请填写需求"
              />
              <button
                type="button"
                onClick={handleSubmitTask}
                disabled={!canSend}
                className={`absolute right-[10px] top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-xl transition ${
                  canSend ? "bg-violet-600 hover:bg-violet-500" : "bg-slate-200"
                }`}
                aria-label={sending ? "处理中" : "发送并生成"}
              >
                {sending ? <LoadingIcon /> : <SendIcon disabled={!canSend} />}
              </button>
            </div>
          </div>
        </section>

        <SessionSidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={setActiveConversationId}
          onDeleteConversation={handleDeleteConversation}
          onNewConversation={handleNewConversation}
        />
      </div>

      {previewState && (previewImageSrc || previewOutput?.url) ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-3 py-4 backdrop-blur-[1px]"
          onClick={handleClosePreview}
          role="dialog"
          aria-modal="true"
          aria-label="图片预览"
        >
          <div
            className="relative w-full max-w-5xl rounded-2xl border border-slate-200/20 bg-slate-900/80 p-2 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              onClick={handleClosePreview}
              className="absolute right-3 top-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-800/80 text-lg text-white transition hover:bg-slate-700"
              aria-label="关闭预览"
            >
              ×
            </button>

            {previewHasMultiple ? (
              <>
                <button
                  type="button"
                  onClick={handlePreviewPrev}
                  className="absolute left-3 top-1/2 z-10 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-slate-800/85 text-xl text-white transition hover:bg-slate-700"
                  aria-label="上一张"
                >
                  ‹
                </button>
                <button
                  type="button"
                  onClick={handlePreviewNext}
                  className="absolute right-3 top-1/2 z-10 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-slate-800/85 text-xl text-white transition hover:bg-slate-700"
                  aria-label="下一张"
                >
                  ›
                </button>
              </>
            ) : null}

            <div className="max-h-[78vh] overflow-hidden rounded-xl bg-slate-950/30">
              <Image
                src={previewImageSrc || previewOutput?.url || ""}
                alt="预览大图"
                width={1600}
                height={1200}
                className="h-auto max-h-[78vh] w-full object-contain"
                unoptimized
              />
            </div>

            <div className="mt-2 flex items-center justify-between px-1 pb-1">
              <div className="text-xs text-slate-200/85">
                {previewState.activeIndex + 1} / {previewState.outputs.length}
              </div>
              <button
                type="button"
                disabled={!previewOutput.downloadUrl}
                onClick={() => {
                  if (!previewOutput.downloadUrl) return;
                  triggerImageDownload(
                    previewOutput.downloadUrl,
                    previewOutput.file_name || `generated_${previewOutput.id}.png`,
                  );
                }}
                className="inline-flex items-center rounded-lg bg-violet-500 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:bg-slate-500"
              >
                下载图片
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <LoginModal
        open={!isAuthenticated}
        loading={authLoading}
        onSubmit={handleLogin}
      />
    </main>
  );
}
