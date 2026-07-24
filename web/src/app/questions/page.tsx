"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Difficulty, Exam, Question } from "@/lib/types";
import { ApiError } from "@/lib/types";
import { difficultyTone, formatDate } from "@/lib/utils";
import {
  Badge,
  Button,
  EmptyState,
  ErrorBanner,
  Field,
  LoadingBlock,
  PageHeader,
  Panel,
  inputClass,
} from "@/components/ui";

const LETTERS = ["A", "B", "C", "D"] as const;

function QuestionCard({
  question,
  reveal,
  onDelete,
  deleting,
}: {
  question: Question;
  reveal?: boolean;
  onDelete?: (id: string) => void;
  deleting?: boolean;
}) {
  const [picked, setPicked] = useState<number | null>(null);
  const show = reveal || picked !== null;

  return (
    <article className="rounded-2xl border border-white/8 bg-[#0c1c24]/80 p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          <Badge className={difficultyTone(question.difficulty)}>
            {question.difficulty}
          </Badge>
          {question.topic ? (
            <Badge className="bg-white/5 text-stone-300 ring-white/10">
              {question.topic}
            </Badge>
          ) : null}
          {question.subject ? (
            <Badge className="bg-white/5 text-stone-300 ring-white/10">
              {question.subject}
            </Badge>
          ) : null}
        </div>
        {onDelete ? (
          <Button
            type="button"
            variant="ghost"
            className="!px-2 !py-1 text-xs text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
            disabled={deleting}
            onClick={() => onDelete(question.id)}
          >
            {deleting ? "Deleting…" : "Delete"}
          </Button>
        ) : null}
      </div>
      <h3 className="font-display text-lg leading-snug text-stone-50">{question.stem}</h3>
      <ul className="mt-4 space-y-2">
        {question.options.map((opt, idx) => {
          const isCorrect = idx === question.correct_index;
          const isPicked = picked === idx;
          let tone = "border-white/8 bg-white/[0.03] hover:bg-white/[0.06]";
          if (show && isCorrect) tone = "border-emerald-400/40 bg-emerald-500/10";
          else if (show && isPicked && !isCorrect)
            tone = "border-rose-400/40 bg-rose-500/10";

          return (
            <li key={`${question.id}-${idx}`}>
              <button
                type="button"
                onClick={() => setPicked(idx)}
                className={`flex w-full items-start gap-3 rounded-xl border px-3 py-3 text-left text-sm transition ${tone}`}
              >
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white/5 font-mono text-xs text-teal-200">
                  {LETTERS[idx]}
                </span>
                <span className="text-stone-200">{opt}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {show && question.explanation ? (
        <p className="mt-4 rounded-xl bg-white/[0.03] px-3 py-3 text-sm leading-relaxed text-stone-400">
          <span className="font-medium text-stone-300">Explanation · </span>
          {question.explanation}
        </p>
      ) : null}
      <p className="mt-3 text-xs text-stone-600">{formatDate(question.created_at)}</p>
    </article>
  );
}

export default function QuestionsPage() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [streamProgress, setStreamProgress] = useState<string | null>(null);

  const [examId, setExamId] = useState("");
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(2);
  const [maxCount, setMaxCount] = useState(10);
  const [difficulty, setDifficulty] = useState<Difficulty | "">("");
  const [filterDifficulty, setFilterDifficulty] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [e, q, health] = await Promise.all([
        api.listExams(),
        api.listQuestions({
          exam_id: examId || undefined,
          difficulty: filterDifficulty || undefined,
          limit: 50,
        }),
        api.health().catch(() => null),
      ]);
      setExams(e);
      if (!examId && e[0]) setExamId(e[0].id);
      setQuestions(q.items);
      setTotal(q.total);
      if (health?.question_generate_max_count) {
        setMaxCount(health.question_generate_max_count);
        setCount((c) => Math.min(c, health.question_generate_max_count!));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load questions");
    } finally {
      setLoading(false);
    }
  }, [examId, filterDifficulty]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onGenerate(e: FormEvent) {
    e.preventDefault();
    if (!examId) return;
    setGenerating(true);
    setError(null);
    setInfo(null);
    setStreamProgress(null);
    const streamed: Question[] = [];
    try {
      for await (const event of api.generateQuestionsStream({
        exam_id: examId,
        topic: topic.trim() || null,
        count,
        difficulty: difficulty || null,
      })) {
        if (event.event === "started") {
          setStreamProgress(
            `Starting · mode ${event.mode} · ${event.context_used} context chunks`,
          );
        } else if (event.event === "slot_started") {
          setStreamProgress(`Generating question ${event.index}/${event.total}…`);
        } else if (event.event === "attempt_failed") {
          setStreamProgress(
            `Question ${event.index}: retrying (attempt ${event.attempt})…`,
          );
        } else if (event.event === "question") {
          streamed.push(event.item);
          setQuestions((prev) => {
            const without = prev.filter((q) => q.id !== event.item.id);
            return [event.item, ...without];
          });
          setStreamProgress(`Received question ${event.index}`);
        } else if (event.event === "done") {
          setInfo(
            `Generated ${event.generated_count}/${event.requested_count} · mode ${event.mode} · ${event.context_used} context chunks`,
          );
          setStreamProgress(null);
        } else if (event.event === "error") {
          throw new ApiError(502, event.error);
        }
      }
      if (!streamed.length) {
        setError("No valid questions were generated. Try again or narrow the topic.");
      }
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Generation failed");
      setStreamProgress(null);
    } finally {
      setGenerating(false);
    }
  }

  async function onDeleteOne(id: string) {
    setDeletingId(id);
    setError(null);
    setInfo(null);
    try {
      await api.deleteQuestion(id);
      setInfo("Question deleted");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  async function onClearAll() {
    if (!total) return;
    const scope = examId ? "for this exam" : "across all exams";
    if (!window.confirm(`Delete all ${total} saved question(s) ${scope}?`)) {
      return;
    }
    setClearing(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.clearQuestions(examId || undefined);
      setInfo(`Cleared ${res.deleted_count} question(s)`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Clear failed");
    } finally {
      setClearing(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Question bank"
        title="Generate & practice MCQs"
        description="Pull hybrid context from processed documents and ask the LLM for IBPS-style multiple-choice questions. Leave topic blank for full-syllabus sampling."
      />

      {error ? (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      ) : null}
      {info ? (
        <div className="mb-6 rounded-xl border border-teal-500/30 bg-teal-500/10 px-4 py-3 text-sm text-teal-100">
          {info}
        </div>
      ) : null}
      {streamProgress ? (
        <div className="mb-6 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-100">
          {streamProgress}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <Panel>
          <h2 className="font-display text-xl text-stone-50">Generate</h2>
          <form className="mt-4 space-y-4" onSubmit={onGenerate}>
            <Field label="Exam">
              <select
                className={inputClass}
                value={examId}
                onChange={(e) => setExamId(e.target.value)}
                required
              >
                {exams.map((exam) => (
                  <option key={exam.id} value={exam.id}>
                    {exam.code} — {exam.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Topic"
              hint="Optional — empty runs full syllabus mode across diverse chunks"
            >
              <input
                className={inputClass}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="RBI monetary policy"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Count" hint={`1–${maxCount}`}>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  max={maxCount}
                  value={count}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    if (Number.isNaN(next)) return;
                    setCount(Math.min(Math.max(1, next), maxCount));
                  }}
                />
              </Field>
              <Field label="Difficulty">
                <select
                  className={inputClass}
                  value={difficulty}
                  onChange={(e) =>
                    setDifficulty(e.target.value as Difficulty | "")
                  }
                >
                  <option value="">Any</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </Field>
            </div>
            <Button type="submit" disabled={generating || !examId}>
              {generating
                ? streamProgress || "Generating… (streaming)"
                : "Generate MCQs"}
            </Button>
          </form>
        </Panel>

        <Panel>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-display text-xl text-stone-50">Saved questions</h2>
              <p className="mt-1 text-sm text-stone-500">{total} total</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Filter difficulty">
                <select
                  className={inputClass}
                  value={filterDifficulty}
                  onChange={(e) => setFilterDifficulty(e.target.value)}
                >
                  <option value="">All</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </Field>
              <Button
                type="button"
                variant="danger"
                disabled={clearing || loading || total === 0}
                onClick={() => void onClearAll()}
              >
                {clearing ? "Clearing…" : "Clear all"}
              </Button>
            </div>
          </div>
          <div className="mt-4">
            {loading ? <LoadingBlock /> : null}
            {!loading && questions.length === 0 ? (
              <EmptyState
                title="No questions yet"
                description="Generate from a processed document, or widen your filters."
              />
            ) : null}
            {!loading && questions.length > 0 ? (
              <div className="max-h-[36rem] space-y-4 overflow-y-auto pr-1">
                {questions.map((q) => (
                  <QuestionCard
                    key={q.id}
                    question={q}
                    onDelete={(id) => void onDeleteOne(id)}
                    deleting={deletingId === q.id}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}
