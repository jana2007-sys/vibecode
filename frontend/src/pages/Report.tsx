/** Interview report page.

When opened with `?session=<session_id>` (from the History page) the report is
fetched from the backend via `GET /api/candidates/{id}/interviews/{sid}/report`
and a "Download PDF" button links to the generated PDF. Without the query
parameter it falls back to the live feedback from the interview context so the
post-interview flow keeps working.
*/

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CheckIcon,
  DownloadIcon,
  SparklesIcon,
} from "../components/ui/Icons";
import { useInterviewContext } from "../context/InterviewContext";
import { api } from "../services/api";
import type { AnswerReview, InterviewReport } from "../types/report";

interface SectionCardProps {
  title: string;
  subtitle: string;
  icon: "strengths" | "gaps" | "next";
  items: string[];
  emptyLabel: string;
}

const sectionStyles = {
  strengths: {
    iconBox: "border-teal-400/30 bg-teal-500/15 text-teal-700 dark:text-teal-300",
    itemIcon: "text-teal-600 dark:text-teal-400",
    symbol: CheckIcon,
  },
  gaps: {
    iconBox: "border-amber-400/30 bg-amber-500/15 text-amber-700 dark:text-amber-300",
    itemIcon: "text-amber-600 dark:text-amber-400",
    symbol: AlertTriangleIcon,
  },
  next: {
    iconBox: "border-sky-400/30 bg-sky-500/15 text-sky-700 dark:text-sky-300",
    itemIcon: "text-sky-600 dark:text-sky-400",
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
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">{title}</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
        </div>
        <span className="inline-flex h-7 min-w-7 shrink-0 items-center justify-center rounded-full border border-teal-400/25 bg-teal-500/10 px-2 text-xs font-bold text-teal-700 dark:text-teal-200">
          {items.length}
        </span>
      </div>
      <ul className="mt-4 space-y-3">
        {items.length > 0 ? (
          items.map((item, index) => (
            <li
              key={`${icon}-${index}`}
              className="flex items-start gap-2.5 text-sm leading-relaxed text-slate-700 dark:text-slate-200"
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

interface ReportBodyProps {
  candidateName: string;
  candidateRole?: string;
  summary: string;
  strengths: string[];
  gaps: string[];
  next: string[];
  overallScore?: number;
  answerReviews?: AnswerReview[];
  onStartAnother: () => void;
  downloadUrl?: string;
}

function AnswerReviewSection({ reviews }: { reviews: AnswerReview[] }) {
  const goodCount = reviews.filter((review) => review.verdict === "Very good").length;

  return (
    <section className="animate-fade-up [animation-delay:320ms]">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-400/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
          <CheckIcon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Answer Review</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Verify each answer and see how it was graded.
          </p>
        </div>
        <span className="inline-flex h-7 min-w-7 shrink-0 items-center justify-center rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2 text-xs font-bold text-emerald-700 dark:text-emerald-200">
          {goodCount}/{reviews.length} good
        </span>
      </div>

      <ul className="mt-4 space-y-4">
        {reviews.map((review) => {
          const good = review.verdict === "Very good";
          return (
            <li key={review.question_id} className="card-glass rounded-2xl p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <p className="text-[15px] font-semibold leading-snug text-slate-900 dark:text-white">
                  {review.question}
                </p>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge tone="slate">{review.score}/10</Badge>
                  <Badge tone={good ? "emerald" : "rose"}>{review.verdict}</Badge>
                </div>
              </div>
              {review.topic_title ? (
                <p className="mt-1 text-xs font-medium text-teal-700 dark:text-teal-300">
                  {review.topic_title}
                </p>
              ) : null}
              {review.answer ? (
                <div className="mt-3 rounded-xl border border-slate-200 bg-white/60 px-4 py-3 dark:border-white/10 dark:bg-white/[0.04]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    Your answer
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
                    {review.answer}
                  </p>
                </div>
              ) : null}
              {review.rationale ? (
                <p className="mt-3 flex items-start gap-2 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                  {good ? (
                    <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  )}
                  <span>{review.rationale}</span>
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ReportBody({
  candidateName,
  candidateRole,
  summary,
  strengths,
  gaps,
  next,
  overallScore,
  answerReviews,
  onStartAnother,
  downloadUrl,
}: ReportBodyProps) {
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div className="animate-fade-up text-center">
        <Badge tone="teal" className="border-teal-400/40 bg-teal-500/15">
          <SparklesIcon className="h-3 w-3" />
          Report
        </Badge>
        <h1 className="mt-4 text-balance text-4xl font-extrabold tracking-tight text-slate-900 dark:text-white sm:text-5xl">
          Interview{" "}
          <span className="text-gradient">Complete</span>
        </h1>
        <p className="mt-3 text-slate-500 dark:text-slate-400">
          {candidateName}
          {candidateRole ? ` · ${candidateRole}` : ""}
          {typeof overallScore === "number" ? ` · Score ${overallScore}%` : ""}
        </p>

        <Card className="mt-8 p-6 text-left">
          <p className="text-xs font-semibold uppercase tracking-wider text-teal-700 dark:text-teal-300">
            Summary
          </p>
          <p className="mt-3 text-[15px] leading-relaxed text-slate-700 dark:text-slate-200">
            {summary}
          </p>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="animate-fade-up [animation-delay:80ms]">
          <SectionCard
            title="Strengths"
            subtitle="What you did well"
            icon="strengths"
            items={strengths}
            emptyLabel="Nothing flagged here — you covered your bases."
          />
        </div>
        <div className="animate-fade-up [animation-delay:160ms]">
          <SectionCard
            title="Areas to improve"
            subtitle="Where to focus next"
            icon="gaps"
            items={gaps}
            emptyLabel="No gaps flagged for this interview."
          />
        </div>
        <div className="animate-fade-up [animation-delay:240ms] md:col-span-2">
          <SectionCard
            title="Next steps"
            subtitle="Concrete suggestions for your learning path"
            icon="next"
            items={next}
            emptyLabel="No next steps to suggest."
          />
        </div>
      </div>

      {answerReviews && answerReviews.length > 0 ? (
        <AnswerReviewSection reviews={answerReviews} />
      ) : null}

      <div className="flex flex-col items-center justify-center gap-3 pt-2 sm:flex-row">
        <Button size="lg" onClick={onStartAnother}>
          Start another interview
          <ArrowRightIcon className="h-4 w-4" />
        </Button>
        {downloadUrl ? (
          <a
            href={downloadUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 px-6 py-3 text-base font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/70 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <DownloadIcon className="h-4 w-4" />
            Download PDF
          </a>
        ) : null}
      </div>
    </div>
  );
}

export function Report() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { candidate, feedback, done, messages, sessionId, reset } = useInterviewContext();

  const [report, setReport] = useState<InterviewReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  const sessionParam = searchParams.get("session");
  const candidateId = candidate?.id ?? null;

  useEffect(() => {
    if (!sessionParam || !candidateId) return;
    let cancelled = false;
    setReportLoading(true);
    setReportError(null);
    api
      .getReport(candidateId, sessionParam)
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch(() => {
        if (!cancelled) setReportError("Couldn't load this report from the backend.");
      })
      .finally(() => {
        if (!cancelled) setReportLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionParam, candidateId]);

  function startAnother() {
    reset();
    navigate("/candidates");
  }

  // Backend report requested via ?session=.
  if (sessionParam) {
    if (reportLoading) {
      return (
        <div className="flex flex-1 items-center justify-center px-4">
          <EmptyState
            title="Loading report…"
            description="Fetching the report from the backend."
          />
        </div>
      );
    }
    if (reportError) {
      if (feedback) {
        const fallbackDownloadUrl =
          candidate && sessionId ? api.reportPdfUrl(candidate.id, sessionId) : undefined;
        return (
          <ReportBody
            candidateName={candidate?.name ?? ""}
            candidateRole={candidate?.role}
            summary={feedback.summary}
            strengths={feedback.strengths}
            gaps={feedback.gaps}
            next={feedback.next}
            onStartAnother={startAnother}
            downloadUrl={fallbackDownloadUrl}
          />
        );
      }
      return (
        <div className="flex flex-1 items-center justify-center px-4">
          <EmptyState
            icon="alert"
            title="Couldn't load the report"
            description={reportError}
            action={<Button onClick={startAnother}>Start another interview</Button>}
          />
        </div>
      );
    }
    if (report) {
      const downloadUrl = candidateId
        ? api.reportPdfUrl(candidateId, report.session_id)
        : undefined;
      return (
        <ReportBody
          candidateName={report.candidate.name}
          candidateRole={report.candidate.role}
          summary={report.feedback.summary}
          strengths={report.feedback.strengths}
          gaps={report.feedback.improvements}
          next={report.feedback.topics.map((topic) => topic.title)}
          overallScore={report.feedback.overall_score}
          answerReviews={report.answer_reviews ?? []}
          onStartAnother={startAnother}
          downloadUrl={downloadUrl}
        />
      );
    }
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
          action={<Button to="/interview">Return to interview</Button>}
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

  const downloadUrl = candidate && sessionId ? api.reportPdfUrl(candidate.id, sessionId) : undefined;

  return (
    <ReportBody
      candidateName={candidate?.name ?? ""}
      candidateRole={candidate?.role}
      summary={feedback.summary}
      strengths={feedback.strengths}
      gaps={feedback.gaps}
      next={feedback.next}
      onStartAnother={startAnother}
      downloadUrl={downloadUrl}
    />
  );
}
