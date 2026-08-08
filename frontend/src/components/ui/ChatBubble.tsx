/** Conversation message bubbles (interviewer + candidate) and a typing state. */

import { type ReactNode } from "react";
import type { ChatMessage } from "../../types/interview";
import { Badge } from "./Badge";
import { RefreshIcon, SparklesIcon, UserIcon } from "./Icons";

export type AssistantKind = "intro" | "question" | "follow_up" | "closing";

interface ChatBubbleProps {
  message: ChatMessage;
  kind?: AssistantKind | null;
  topicTitle?: string | null;
  candidateName?: string;
}

function Avatar({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
      {children}
    </div>
  );
}

export function ChatBubble({
  message,
  kind = null,
  topicTitle = null,
  candidateName = "You",
}: ChatBubbleProps) {
  const isAssistant = message.role === "assistant";

  if (isAssistant) {
    const showFollowUp = kind === "follow_up";
    return (
      <div className="flex animate-message-in items-start gap-3">
        <Avatar>
          <SparklesIcon className="h-4 w-4" />
        </Avatar>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-300">
              InterVue AI
            </span>
            {showFollowUp ? (
              <Badge
                tone="violet"
                className="animate-follow-up-in border-violet-400/40 bg-violet-500/20"
              >
                <SparklesIcon className="h-3 w-3" />
                Follow-up
              </Badge>
            ) : null}
            {topicTitle ? (
              <Badge tone="slate" className="border-white/10">
                {topicTitle}
              </Badge>
            ) : null}
          </div>
          <div className="max-w-[92%] rounded-2xl rounded-tl-md border border-white/10 bg-white/[0.06] px-4 py-3 text-[15px] leading-relaxed text-slate-100 shadow-lg shadow-black/10 backdrop-blur-sm sm:max-w-[78%]">
            <p className="whitespace-pre-line">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex animate-message-in items-start justify-end gap-3">
      <div className="max-w-[92%] space-y-1.5 sm:max-w-[78%]">
        <div className="flex justify-end">
          <span className="text-xs font-semibold text-slate-400">
            {candidateName}
          </span>
        </div>
        <div className="rounded-2xl rounded-tr-md bg-gradient-to-br from-indigo-500 to-violet-600 px-4 py-3 text-[15px] leading-relaxed text-white shadow-lg shadow-indigo-500/20">
          <p className="whitespace-pre-line">{message.content}</p>
        </div>
      </div>
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-300">
        <UserIcon className="h-4 w-4" />
      </div>
    </div>
  );
}

/** Rendered while waiting for the backend to respond. */
export function ThinkingBubble() {
  return (
    <div className="flex animate-message-in items-start gap-3" aria-live="polite">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
        <SparklesIcon className="h-4 w-4" />
      </div>
      <div className="flex items-center gap-2 rounded-2xl rounded-tl-md border border-white/10 bg-white/[0.06] px-4 py-3.5">
        <RefreshIcon className="h-4 w-4 animate-spin text-indigo-300" />
        <span className="flex items-center gap-1.5 text-sm text-slate-400">
          <span className="mr-1">AI is thinking</span>
          <span className="h-1.5 w-1.5 animate-blink rounded-full bg-indigo-300 [animation-delay:0ms]" />
          <span className="h-1.5 w-1.5 animate-blink rounded-full bg-violet-300 [animation-delay:200ms]" />
          <span className="h-1.5 w-1.5 animate-blink rounded-full bg-fuchsia-300 [animation-delay:400ms]" />
        </span>
      </div>
    </div>
  );
}
