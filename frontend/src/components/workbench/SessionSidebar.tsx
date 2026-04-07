"use client";

import type { Conversation } from "@/src/types/conversation";

type SessionSidebarProps = {
  conversations: Conversation[];
  activeConversationId: string;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
  onNewConversation: () => void;
};

export function SessionSidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  onNewConversation,
}: SessionSidebarProps) {
  return (
    <aside className="order-3 flex min-h-0 flex-col rounded-2xl border border-slate-200/80 bg-white/70 shadow-[0_8px_24px_rgba(30,41,59,0.06)] backdrop-blur">
      <div className="flex h-full min-h-0 flex-col divide-y divide-slate-200/80">
        <div className="flex items-center justify-between px-3 py-2.5 sm:px-4">
          <span className="text-sm font-semibold text-slate-700">对话列表</span>
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700 transition hover:bg-violet-100"
            onClick={onNewConversation}
            aria-label="新建对话"
          >
            +新对话
          </button>
        </div>
        <div className="flex flex-1 flex-col gap-2.5 overflow-y-auto px-3 py-2.5 sm:px-4">
          {conversations.map((conversation) => (
            <div key={conversation.conversation_id} className="group relative">
              <button
                type="button"
                onClick={() => onSelectConversation(conversation.conversation_id)}
                className={`w-full rounded-lg border px-2 py-1 text-left transition ${
                  activeConversationId === conversation.conversation_id
                    ? "border-violet-300 bg-violet-50/90 text-violet-800 shadow-[0_4px_12px_rgba(124,58,237,0.15)]"
                    : "border-slate-200/90 bg-white/80 text-slate-700 hover:bg-slate-100/70"
                }`}
              >
                <div className="truncate pr-5 text-sm font-medium leading-5">{conversation.title}</div>
                <div
                  className={`mt-0.5 truncate text-[10px] ${
                    activeConversationId === conversation.conversation_id ? "text-violet-400/90" : "text-slate-400/80"
                  }`}
                >
                  {new Date(conversation.updated_at).toLocaleString()}
                </div>
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onDeleteConversation(conversation.conversation_id);
                }}
                className="absolute right-1.5 top-1.5 hidden h-5 w-5 items-center justify-center rounded-md border border-slate-200 bg-white/95 text-[11px] text-slate-500 shadow-sm transition hover:border-rose-200 hover:text-rose-600 group-hover:inline-flex"
                aria-label="删除对话"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
