/** Interview report page. */

import { useNavigate } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CheckIcon,
  SparklesIcon,
} from "../components/ui/Icons";
import { useInterviewContext } from "../context/InterviewContext";

interface SectionCardProps {
  title: string;
  subtitle: string;
  icon: "strengths" | "gaps" | "next";
  items: string[];
  emptyLabel: string;
}

const sectionStyles = {
  strengths: {
    iconBox: "border-emerald-400/30 bg-emerald-500/15 text-emerald-300",
    itemIcon: "text-emerald-400",
    symbol: CheckIcon,
  },
  gaps: {
    iconBox: "border-amber-400/30 bg-amber-500/15 text-amber-300",
    itemIcon: "text-amber-400",
    symbol: AlertTriangleIcon,
  },
  next: {
    iconBox: "border-violet-400/30 bg-violet-500/15 text-violet-300",
    itemIcon: "text-violet-400",
    symbol: ArrowRightIcon,
  },
} as const;

function SectionCard({
  title,
  subtitle,
  icon,
  items,
  emptyLabel,
}: SectionCardProps) {
  const styles = sectionStyles[icon];
  const Symbol = styles.symbol;

  return (
    <Card className="p-6">
      <div className="flex items-center gap-3">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-xl border ${styles.iconBox}`}
        >
          <Symbol className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <p className="text-xs text-slate-400">{subtitle}</p>
        </div>
      </div>
      <ul className="mt-4 space-y-3">
        {items.length > 0 ? (
          items.map((item, index) => (
            <li
              key={`${icon}-${index}`}
              className="flex items-start gap-2.5 text-sm leading-relaxed text-slate-200"
            >
              <Symbol className={`mt-0.5 h-4 w-4 shrink-0 ${styles.itemIcon}`} />
              <span>{item}</span>
            </li>
          ))
        ) : (
          <li className="text-sm text-slate-500">{emptyLabel}</li>
        )}
      </ul>
    </Card>
  );
}

export function Report() {
  const navigate = useNavigate();
  const { candidate, feedback, done, messages, reset } = useInterviewContext();

  function startAnother() {
    // Clear both in-memory session state and the persisted session.
    reset();
    navigate("/candidates");
  }

  // No interview has ever been started.
  if (!candidate && !feedback) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <EmptyState
          title="No report yet"
          description="Complete a technical interview with InterVue AI and your structured feedback will appear here."
          action={
            <Button to="/candidates" size="lg">
              Start an interview
            </Button>
          }
        />
      </div>
    );
  }

  // Session started but not finished.
  if (!feedback && !done) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <EmptyState
          title="Your report is on the way"
          description={
            messages.length > 0
              ? "Keep going — the report is generated once the interview completes."
              : "Start the interview to get started."
          }
          action={
            <Button to="/interview">
              Return to interview
            </Button>
          }
        />
      </div>
    );
  }

  // Interview finished but the backend returned no feedback payload.
  if (!feedback) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <EmptyState
          icon="alert"
          title="No feedback was returned"
          description="The interview completed, but the service didn't return a feedback report. Please try another interview."
          action={<Button onClick={startAnother}>Start another interview</Button>}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      {/* Hero */}
      <div className="animate-fade-up text-center">
        <Badge tone="emerald" className="border-emerald-400/40 bg-emerald-500/15">
          <SparklesIcon className="h-3 w-3" />
          Report
        </Badge>
        <h1 className="mt-4 text-balance text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
          Interview{" "}
          <span className="text-gradient">Complete</span>
        </h1>
        <p className="mt-3 text-slate-400">
          {candidate?.name}
          {candidate?.role ? ` · ${candidate.role}` : ""}
        </p>

        <Card className="mt-8 p-6 text-left">
          <p className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
            Summary
          </p>
          <p className="mt-3 text-[15px] leading-relaxed text-slate-200">
            {feedback.summary}
          </p>
        </Card>
      </div>

      {/* Feedback sections */}
      <div className="grid gap-6 md:grid-cols-2">
        <div className="animate-fade-up [animation-delay:80ms]">
          <SectionCard
            title="Strengths"
            subtitle="What you did well"
            icon="strengths"
            items={feedback.strengths}
            emptyLabel="Nothing flagged here — you covered your bases."
          />
        </div>
        <div className="animate-fade-up [animation-delay:160ms]">
          <SectionCard
            title="Areas to improve"
            subtitle="Where to focus next"
            icon="gaps"
            items={feedback.gaps}
            emptyLabel="No gaps flagged for this interview."
          />
        </div>
        <div className="animate-fade-up [animation-delay:240ms] md:col-span-2">
          <SectionCard
            title="Next steps"
            subtitle="Concrete suggestions for your learning path"
            icon="next"
            items={feedback.next}
            emptyLabel="No next steps to suggest."
          />
        </div>
      </div>

      <div className="flex justify-center pt-2">
        <Button size="lg" onClick={startAnother}>
          Start another interview
          <ArrowRightIcon className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
