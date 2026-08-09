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
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white shadow-lg shadow-teal-500/30 ring-1 ring-inset ring-white/25 dark:ring-white/10">
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
            <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              InterVue AI
            </span>
            {showFollowUp ? (
              <Badge
                tone="amber"
                className="animate-follow-up-in shadow-[0_0_15px_-4px_rgba(245,158,11,0.5)]"
              >
                <SparklesIcon className="h-3 w-3" />
                Follow-up
              </Badge>
            ) : null}
            {topicTitle ? (
              <Badge tone="slate">{topicTitle}</Badge>
            ) : null}
          </div>
          <div className="max-w-[92%] rounded-2xl rounded-tl-md border border-slate-200 bg-white/70 px-4 py-3 text-[15px] leading-relaxed text-slate-800 shadow-[inset_3px_0_0_rgba(20,184,166,0.5),0_8px_25px_-12px_rgba(6,182,212,0.25)] backdrop-blur-sm dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-100 dark:shadow-[inset_3px_0_0_rgba(20,184,166,0.35),0_8px_25px_-12px_rgba(6,182,212,0.3)] sm:max-w-[78%]">
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
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
            {candidateName}
          </span>
        </div>
        <div className="rounded-2xl rounded-tr-md bg-gradient-to-br from-teal-500 via-cyan-500 to-sky-400 px-4 py-3 text-[15px] leading-relaxed text-white shadow-lg shadow-teal-500/25 ring-1 ring-inset ring-white/20 dark:ring-white/10">
          <p className="whitespace-pre-line">{message.content}</p>
        </div>
      </div>
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
        <UserIcon className="h-4 w-4" />
      </div>
    </div>
  );
}

/** Rendered while waiting for the backend to respond. */
export function ThinkingBubble() {
  return (
    <div className="flex animate-message-in items-start gap-3" aria-live="polite">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-500 text-white shadow-lg shadow-teal-500/30 ring-1 ring-inset ring-white/25 dark:ring-white/10">
        <SparklesIcon className="h-4 w-4" />
      </div>
      <div className="flex items-center gap-2 rounded-2xl rounded-tl-md border border-slate-200 bg-white/70 px-4 py-3.5 dark:border-white/10 dark:bg-white/[0.06]">
        <RefreshIcon className="h-4 w-4 animate-spin text-teal-500 dark:text-teal-300" />
        <span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
          <span className="mr-1">AI is thinking</span>
          <span className="h-1.5 w-1.5 animate-blink rounded-full bg-teal-500 [animation-delay:0ms] dark:bg-teal-300" />
          <span className="h-1.5 w-1.5 animate-blink rounded-full bg-cyan-500 [animation-delay:200ms] dark:bg-cyan-300" />
          <span className="h-1.5 w-1.5 animate-blink rounded-full bg-sky-500 [animation-delay:400ms] dark:bg-sky-300" />
        </span>
      </div>
    </div>
  );
}
