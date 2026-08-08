/** Live interview page — the centerpiece of the app.

Renders the conversational panel driven entirely by the backend: the first
`POST /interview` call (start) produces the first interviewer message, and every
answer is a `POST /interview` call whose reply is displayed verbatim. The
frontend never generates questions.
*/

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type FormEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ChatBubble, ThinkingBubble } from "../components/ui/ChatBubble";
import { EmptyState } from "../components/ui/EmptyState";
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CheckIcon,
  SendIcon,
  SparklesIcon,
} from "../components/ui/Icons";
import { ProgressBar } from "../components/ui/ProgressBar";
import { useInterviewContext } from "../context/InterviewContext";
import { matchQuestion } from "../data/curriculum";
import {
  classifyAssistantMessage,
  computeProgress,
} from "../lib/interview";

export function Interview() {
  const {
    candidate,
    sessionId,
    messages,
    done,
    loading,
    error,
    startInterview,
    submitAnswer,
  } = useInterviewContext();
  const navigate = useNavigate();
  const [answer, setAnswer] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const navigatedRef = useRef(false);

  const progress = useMemo(() => computeProgress(messages), [messages]);

  // Keep the newest messages in view.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  // On completion, give the closing message a moment, then open the report.
  useEffect(() => {
    if (done && !navigatedRef.current) {
      navigatedRef.current = true;
      const timer = setTimeout(() => navigate("/report"), 1600);
      return () => clearTimeout(timer);
    }
  }, [done, navigate]);

  async function handleSubmit(event?: FormEvent) {
    event?.preventDefault();
    const text = answer.trim();
    if (!text || loading) return;
    const ok = await submitAnswer(text);
    if (ok) setAnswer("");
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void handleSubmit();
    }
  }

  // --- States -----------------------------------------------------------------

  // No candidate selected at all.
  if (!candidate) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <EmptyState
          title="No interview in progress"
          description="Select a candidate and we'll personalize a technical interview around their learning journey."
          action={
            <Button to="/candidates" size="lg">
              Choose a candidate
            </Button>
          }
        />
      </div>
    );
  }

  // Waiting for the backend to start the interview.
  if (loading && !sessionId && messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
        <div className="flex h-16 w-16 animate-float items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-glow-strong">
          <SparklesIcon className="h-8 w-8" />
        </div>
        <p className="text-lg font-semibold text-white">AI is thinking…</p>
        <p className="text-sm text-slate-500">
          Preparing a personalized interview for {candidate.name}
        </p>
      </div>
    );
  }

  // Start failed — offer a retry.
  if (error && !sessionId && messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <EmptyState
          icon="alert"
          title="Unable to start the interview"
          description={error}
          action={
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button
                onClick={() => void startInterview(candidate)}
                loading={loading}
              >
                Try again
              </Button>
              <Button to="/candidates" variant="secondary">
                Choose a candidate
              </Button>
            </div>
          }
        />
      </div>
    );
  }

  // A candidate is set but the session hasn't started (e.g. refresh mid-start).
  if (!sessionId && messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <Card className="w-full max-w-lg p-8 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-glow">
            <SparklesIcon className="h-7 w-7" />
          </div>
          <h2 className="mt-5 text-2xl font-bold tracking-tight text-white">
            Ready for your technical interview?
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">
            {candidate.name} will be asked curriculum-grounded questions, and
            the interviewer will adapt follow-ups to each answer.
          </p>
          <Button
            className="mt-6 w-full"
            size="lg"
            onClick={() => void startInterview(candidate)}
            loading={loading}
          >
            Begin Interview
            <ArrowRightIcon className="h-4 w-4" />
          </Button>
        </Card>
      </div>
    );
  }

  // --- Active conversation ----------------------------------------------------

  const candidateName = candidate.name.split(" ")[0] ?? "You";
  const isCompleted = done;

  return (
    <div className="mx-auto flex h-[calc(100dvh-3.5rem)] w-full max-w-5xl flex-col gap-3 px-3 py-3 sm:gap-4 sm:px-6 sm:py-4">
      {/* Header */}
      <header className="glass shrink-0 px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
              <SparklesIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-white">
                Technical Interview
              </p>
              <p className="truncate text-xs text-slate-400">
                {candidate.name}
                {candidate.role ? ` · ${candidate.role}` : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {progress.topicTitle ? (
              <Badge tone="slate" className="hidden sm:inline-flex">
                {progress.topicTitle}
              </Badge>
            ) : null}
            <span className="whitespace-nowrap text-sm font-semibold text-slate-200">
              Question {progress.current} of {progress.totalQuestions}
            </span>
          </div>
        </div>
        <div className="mt-3">
          <ProgressBar
            value={progress.current}
            max={progress.totalQuestions}
            ariaLabel={`Question ${progress.current} of ${progress.totalQuestions}`}
          />
        </div>
      </header>

      {/* Messages */}
      <div
        ref={listRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        className="glass flex-1 space-y-5 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6"
      >
        {messages.map((message, index) => {
          const kind =
            message.role === "assistant"
              ? classifyAssistantMessage(messages, index, done)
              : null;
          const topicTitle =
            message.role === "assistant"
              ? (matchQuestion(message.content)?.topicTitle ?? null)
              : null;
          return (
            <ChatBubble
              key={message.id}
              message={message}
              kind={kind}
              topicTitle={topicTitle}
              candidateName={candidateName}
            />
          );
        })}
        {loading ? <ThinkingBubble /> : null}
      </div>

      {/* Completion panel or answer input */}
      {isCompleted ? (
        <div className="glass-strong flex shrink-0 flex-col items-center justify-between gap-4 px-4 py-4 sm:flex-row sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-400/30 bg-emerald-500/15 text-emerald-300">
              <CheckIcon className="h-5 w-5" />
            </div>
            <div>
              <p className="font-semibold text-white">Interview complete</p>
              <p className="text-sm text-slate-400">
                Opening your report…
              </p>
            </div>
          </div>
          <Button to="/report" className="w-full sm:w-auto">
            View Report
            <ArrowRightIcon className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="glass-strong flex shrink-0 flex-col gap-3 px-4 py-4 sm:px-5"
        >
          {error ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-200"
            >
              <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-semibold">Your answer wasn't sent.</p>
                <p className="text-rose-300/90">{error}</p>
              </div>
            </div>
          ) : null}

          <label htmlFor="answer-input" className="sr-only">
            Your answer
          </label>
          <textarea
            id="answer-input"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={4}
            placeholder="Explain your approach…"
            aria-label="Your answer"
            className="w-full resize-none rounded-xl border border-white/10 bg-ink-900/60 px-4 py-3 text-[15px] leading-relaxed text-slate-100 placeholder:text-slate-500 transition-colors focus:border-indigo-400/50 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />
          <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="hidden text-xs text-slate-500 sm:block">
              Enter to submit · Shift+Enter for a new line
            </p>
            <Button
              type="submit"
              size="lg"
              disabled={loading || answer.trim().length === 0}
              loading={loading}
              className="w-full sm:w-auto"
            >
              Submit Answer
              <SendIcon className="h-4 w-4" />
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
