import type { WorkbenchDraft } from "@/src/types/workbench";

export type SystemStatus = "processing" | "done" | "error" | "cancelled";

export type GeneratedOutput = {
  id: string;
  kind: "image";
  url?: string;
  preview_url?: string;
  modal_preview_url?: string;
  downloadUrl?: string;
  file_path?: string;
  file_name?: string;
  status: "placeholder" | "ready" | "failed";
};

export type ConversationMessage = {
  id: string;
  created_at: number;
  task_id?: string;
  user_input: string;
  system_status: SystemStatus;
  generated_outputs: GeneratedOutput[];
  optimized_prompt?: string;
  size_text?: string;
  style_preference?: string;
  error_message?: string;
  progress_current?: number;
  progress_total?: number;
  progress_message?: string;
};

export type Conversation = {
  conversation_id: string;
  title: string;
  created_at: number;
  updated_at: number;
  messages: ConversationMessage[];
};

export type ConversationState = {
  session_id: string;
  active_conversation_id: string;
  conversations: Conversation[];
  draft_by_conversation_id: Record<string, WorkbenchDraft>;
};
