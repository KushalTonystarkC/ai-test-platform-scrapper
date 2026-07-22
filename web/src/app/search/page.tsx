"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Exam, SearchHit, SearchMode } from "@/lib/types";
import { ApiError } from "@/lib/types";
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

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "hybrid", label: "Hybrid", hint: "Keyword + semantic blend" },
  { value: "semantic", label: "Semantic", hint: "Embedding similarity" },
  { value: "keyword", label: "Keyword", hint: "pg_trgm / full text" },
];

export default function SearchPage() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [examId, setExamId] = useState("");
  const [q, setQ] = useState("RBI monetary policy");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const boot = useCallback(async () => {
    setBooting(true);
    try {
      const e = await api.listExams();
      setExams(e);
      if (e[0]) setExamId(e[0].id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load exams");
    } finally {
      setBooting(false);
    }
  }, []);

  useEffect(() => {
    void boot();
  }, [boot]);

  async function onSearch(e?: FormEvent) {
    e?.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const res = await api.search({
        q: q.trim(),
        mode,
        exam_id: examId || undefined,
        limit: 12,
      });
      setHits(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
      setHits([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Retrieval"
        title="Hybrid search"
        description="Query the knowledge base with keyword, semantic, or hybrid ranking across embedded chunks."
      />

      {error ? (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      ) : null}

      <Panel>
        {booting ? (
          <LoadingBlock label="Loading exams…" />
        ) : (
          <form className="space-y-4" onSubmit={onSearch}>
            <Field label="Query">
              <input
                className={inputClass}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="e.g. monetary policy transmission"
                required
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Exam scope">
                <select
                  className={inputClass}
                  value={examId}
                  onChange={(e) => setExamId(e.target.value)}
                >
                  <option value="">All exams</option>
                  {exams.map((exam) => (
                    <option key={exam.id} value={exam.id}>
                      {exam.code}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Mode">
                <div className="grid grid-cols-3 gap-2">
                  {MODES.map((m) => (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => setMode(m.value)}
                      className={`rounded-xl px-2 py-2.5 text-left text-sm ring-1 transition ${
                        mode === m.value
                          ? "bg-teal-400/15 text-teal-100 ring-teal-400/40"
                          : "bg-white/5 text-stone-400 ring-white/10 hover:bg-white/8"
                      }`}
                    >
                      <span className="block font-medium">{m.label}</span>
                      <span className="mt-0.5 block text-[11px] opacity-70">{m.hint}</span>
                    </button>
                  ))}
                </div>
              </Field>
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? "Searching…" : "Search"}
            </Button>
          </form>
        )}
      </Panel>

      <div className="mt-6">
        {loading ? <LoadingBlock label="Retrieving chunks…" /> : null}
        {!loading && searched && hits.length === 0 ? (
          <EmptyState
            title="No hits"
            description="Try another query, switch mode, or process more documents first."
          />
        ) : null}
        {!loading && hits.length > 0 ? (
          <>
            <p className="mb-4 text-sm text-stone-500">
              Showing {hits.length} of {total} results
            </p>
            <ul className="space-y-4">
              {hits.map((hit) => (
                <li key={hit.chunk_id}>
                  <Panel className="!p-4">
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <Badge className="bg-teal-400/15 text-teal-200 ring-teal-400/30">
                        score {hit.score.toFixed(3)}
                      </Badge>
                      {hit.keyword_score != null ? (
                        <Badge className="bg-white/5 text-stone-300 ring-white/10">
                          kw {hit.keyword_score.toFixed(3)}
                        </Badge>
                      ) : null}
                      {hit.semantic_score != null ? (
                        <Badge className="bg-white/5 text-stone-300 ring-white/10">
                          sem {hit.semantic_score.toFixed(3)}
                        </Badge>
                      ) : null}
                      <span className="text-xs text-stone-500">
                        page {hit.page_number} · chunk {hit.chunk_index}
                      </span>
                    </div>
                    {hit.summary ? (
                      <p className="mb-2 text-sm font-medium text-stone-200">{hit.summary}</p>
                    ) : null}
                    <p className="line-clamp-6 whitespace-pre-wrap text-sm leading-relaxed text-stone-400">
                      {hit.content}
                    </p>
                    {typeof hit.metadata?.topic === "string" && hit.metadata.topic ? (
                      <p className="mt-3 text-xs text-teal-300/70">
                        Topic: {hit.metadata.topic}
                        {typeof hit.metadata.subject === "string" && hit.metadata.subject
                          ? ` · ${hit.metadata.subject}`
                          : ""}
                      </p>
                    ) : null}
                  </Panel>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
    </div>
  );
}
