import type {
  Conversation,
  ConversationMessage,
  ConversationState,
  GeneratedOutput,
  SystemStatus,
} from "@/src/types/conversation";
import type { WorkbenchDraft } from "@/src/types/workbench";
import { createEmptyWorkbenchDraft } from "@/src/types/workbench";

export const STORAGE_KEYS = {
  sessionId: "ai_image_workbench_session_id",
  conversations: "ai_image_workbench_conversations",
  activeConversationId: "ai_image_workbench_active_conversation_id",
  draftByConversationId: "ai_image_workbench_draft_by_conversation_id",
} as const;

export const createId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

export const createConversation = (title = "新对话"): Conversation => {
  const now = Date.now();
  return {
    conversation_id: createId(),
    title,
    created_at: now,
    updated_at: now,
    messages: [],
  };
};

export const createGeneratedOutputPlaceholder = (): GeneratedOutput => ({
  id: createId(),
  kind: "image",
  status: "placeholder",
});

export const createMessage = (payload: {
  task_id?: string;
  user_input: string;
  system_status: SystemStatus;
  optimized_prompt?: string;
  size_text?: string;
  style_preference?: string;
  error_message?: string;
  progress_current?: number;
  progress_total?: number;
  progress_message?: string;
}): ConversationMessage => ({
  id: createId(),
  created_at: Date.now(),
  task_id: payload.task_id,
  user_input: payload.user_input,
  system_status: payload.system_status,
  generated_outputs: [createGeneratedOutputPlaceholder()],
  optimized_prompt: payload.optimized_prompt,
  size_text: payload.size_text,
  style_preference: payload.style_preference,
  error_message: payload.error_message,
  progress_current: payload.progress_current,
  progress_total: payload.progress_total,
  progress_message: payload.progress_message,
});

const parseConversations = (raw: string | null): Conversation[] => {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as Conversation[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const parseDraftByConversationId = (raw: string | null): Record<string, WorkbenchDraft> => {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, WorkbenchDraft>;
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).map(([conversationId, draft]) => {
        const empty = createEmptyWorkbenchDraft();
        const references = draft?.references || empty.references;
        return [
          conversationId,
          {
            ...empty,
            ...draft,
            references: {
              product: Array.isArray(references.product) ? references.product : [],
              composition: Array.isArray(references.composition) ? references.composition : [],
              pose: Array.isArray(references.pose) ? references.pose : [],
              style: Array.isArray(references.style) ? references.style : [],
            },
            reserved: {
              ...empty.reserved,
              ...(draft?.reserved || {}),
            },
          } satisfies WorkbenchDraft,
        ];
      }),
    );
  } catch {
    return {};
  }
};

export const getOrCreateSessionId = (): string => {
  const existing = localStorage.getItem(STORAGE_KEYS.sessionId);
  if (existing) return existing;

  const newId = createId();
  localStorage.setItem(STORAGE_KEYS.sessionId, newId);
  return newId;
};

export const loadConversationState = (): ConversationState => {
  const session_id = getOrCreateSessionId();
  const conversations = parseConversations(localStorage.getItem(STORAGE_KEYS.conversations));
  const draft_by_conversation_id = parseDraftByConversationId(
    localStorage.getItem(STORAGE_KEYS.draftByConversationId),
  );

  if (!conversations.length) {
    const first = createConversation();
    return {
      session_id,
      active_conversation_id: first.conversation_id,
      conversations: [first],
      draft_by_conversation_id,
    };
  }

  const storedActiveId = localStorage.getItem(STORAGE_KEYS.activeConversationId);
  const matched = conversations.find((item) => item.conversation_id === storedActiveId);

  return {
    session_id,
    active_conversation_id: matched ? matched.conversation_id : conversations[0].conversation_id,
    conversations,
    draft_by_conversation_id,
  };
};

export const persistConversationState = (params: {
  session_id: string;
  active_conversation_id: string;
  conversations: Conversation[];
  draft_by_conversation_id: Record<string, WorkbenchDraft>;
}) => {
  localStorage.setItem(STORAGE_KEYS.sessionId, params.session_id);
  localStorage.setItem(STORAGE_KEYS.activeConversationId, params.active_conversation_id);
  localStorage.setItem(STORAGE_KEYS.conversations, JSON.stringify(params.conversations));
  localStorage.setItem(
    STORAGE_KEYS.draftByConversationId,
    JSON.stringify(params.draft_by_conversation_id),
  );
};
