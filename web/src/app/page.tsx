"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Document, Exam, HealthResponse, Question } from "@/lib/types";
import { ApiError } from "@/lib/types";
import { formatDate, statusTone } from "@/lib/utils";
import {
  Badge,
  Button,
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  PageHeader,
  Panel,
} from "@/components/ui";

const pipeline = [
  { step: "01", title: "Upload", body: "Drop books, PYQs, or syllabi as PDFs." },
  {
    step: "02",
    title: "Process",
    body: "Extract text, chunk semantically, enrich with LLM metadata.",
  },
  {
    step: "03",
    title: "Embed",
    body: "Store vectors in pgvector for hybrid retrieval.",
  },
  {
    step: "04",
    title: "Generate",
    body: "Pull context and produce exam-style MCQs.",
  },
];

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [exams, setExams] = useState<Exam[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, e, d, q] = await Promise.all([
        api.health().catch(() => null),
        api.listExams(),
        api.listDocuments({ limit: 8 }),
        api.listQuestions({ limit: 6 }),
      ]);
      setHealth(h);
      setExams(e);
      setDocuments(d.items);
      setQuestions(q.items);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not reach the API. Is uvicorn running on :8000?";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const processed = documents.filter((d) => d.status === "PROCESSED").length;
  const processing = documents.filter((d) => d.status === "PROCESSING").length;

  return (
    <div>
      <PageHeader
        eyebrow="Phase 1 showcase"
        title="Turn study PDFs into a searchable question bank."
        description="Upload exam materials, watch them become embedded knowledge chunks, then generate IBPS-style MCQs grounded in your corpus."
        actions={
          <>
            <Link href="/documents">
              <Button>Upload PDF</Button>
            </Link>
            <Link href="/questions">
              <Button variant="secondary">Generate MCQs</Button>
            </Link>
          </>
        }
      />

      {error ? (
        <div className="mb-6 space-y-3">
          <ErrorBanner message={error} />
          <Button variant="secondary" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      ) : null}

      {loading ? <LoadingBlock label="Loading workspace…" /> : null}

      {!loading && !error ? (
        <>
          <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                label: "API",
                value: health?.status === "ok" ? "Online" : "Unknown",
                meta: health ? `v${health.version}` : "—",
              },
              { label: "Exams", value: String(exams.length), meta: "seeded catalogs" },
              {
                label: "Documents",
                value: String(documents.length),
                meta: `${processed} processed · ${processing} running`,
              },
              {
                label: "Questions",
                value: String(questions.length),
                meta: "generated MCQs",
              },
            ].map((stat) => (
              <Panel key={stat.label} className="!p-4">
                <p className="text-xs uppercase tracking-wide text-stone-500">
                  {stat.label}
                </p>
                <p className="mt-2 font-display text-3xl text-stone-50">{stat.value}</p>
                <p className="mt-1 text-xs text-stone-500">{stat.meta}</p>
              </Panel>
            ))}
          </div>

          <div className="mb-8 grid gap-4 lg:grid-cols-4">
            {pipeline.map((item) => (
              <Panel key={item.step} className="!p-4">
                <p className="font-mono text-xs text-teal-300/80">{item.step}</p>
                <h2 className="mt-2 font-display text-xl text-stone-50">{item.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-stone-400">{item.body}</p>
              </Panel>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-display text-xl text-stone-50">Recent documents</h2>
                <Link href="/documents" className="text-sm text-teal-300 hover:text-teal-200">
                  View all
                </Link>
              </div>
              {documents.length === 0 ? (
                <EmptyState
                  title="No documents yet"
                  description="Upload a PDF under Documents to start the ingestion pipeline."
                />
              ) : (
                <ul className="space-y-3">
                  {documents.map((doc) => (
                    <li
                      key={doc.id}
                      className="flex items-start justify-between gap-3 rounded-xl bg-white/[0.03] px-3 py-3"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-stone-100">
                          {doc.title}
                        </p>
                        <p className="mt-1 text-xs text-stone-500">
                          {doc.document_type.replaceAll("_", " ")} · {doc.chunk_count} chunks ·{" "}
                          {formatDate(doc.created_at)}
                        </p>
                      </div>
                      <Badge className={statusTone(doc.status)}>{doc.status}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-display text-xl text-stone-50">Latest questions</h2>
                <Link href="/questions" className="text-sm text-teal-300 hover:text-teal-200">
                  Open bank
                </Link>
              </div>
              {questions.length === 0 ? (
                <EmptyState
                  title="No MCQs yet"
                  description="Process at least one document, then generate questions by topic or full syllabus."
                />
              ) : (
                <ul className="space-y-3">
                  {questions.map((q) => (
                    <li key={q.id} className="rounded-xl bg-white/[0.03] px-3 py-3">
                      <p className="line-clamp-2 text-sm text-stone-100">{q.stem}</p>
                      <p className="mt-2 text-xs text-stone-500">
                        {q.topic || "General"} · {q.difficulty}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}
