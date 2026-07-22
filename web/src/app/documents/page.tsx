"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  Document,
  DocumentChunk,
  DocumentType,
  Exam,
} from "@/lib/types";
import { ApiError } from "@/lib/types";
import { formatBytes, formatDate, statusTone } from "@/lib/utils";
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

const DOC_TYPES: DocumentType[] = ["BOOK", "PREVIOUS_YEAR_PAPER", "SYLLABUS"];

export default function DocumentsPage() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const [examId, setExamId] = useState("");
  const [title, setTitle] = useState("");
  const [documentType, setDocumentType] = useState<DocumentType>("BOOK");
  const [file, setFile] = useState<File | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [e, d] = await Promise.all([
        api.listExams(),
        api.listDocuments({ limit: 100 }),
      ]);
      setExams(e);
      setDocuments(d.items);
      if (!examId && e[0]) setExamId(e[0].id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [examId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while any document is processing
  useEffect(() => {
    const busy = documents.some((d) => d.status === "PROCESSING");
    if (!busy) return;
    const id = window.setInterval(() => {
      void api.listDocuments({ limit: 100 }).then((d) => setDocuments(d.items));
    }, 3000);
    return () => window.clearInterval(id);
  }, [documents]);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!file || !examId || !title.trim()) return;
    setUploading(true);
    setError(null);
    try {
      const doc = await api.uploadDocument({
        file,
        exam_id: examId,
        title: title.trim(),
        document_type: documentType,
      });
      setTitle("");
      setFile(null);
      await load();
      setSelectedId(doc.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function onProcess(id: string) {
    setProcessingId(id);
    setError(null);
    try {
      await api.processDocument(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to queue processing");
    } finally {
      setProcessingId(null);
    }
  }

  async function openChunks(id: string) {
    setSelectedId(id);
    setChunksLoading(true);
    setError(null);
    try {
      const res = await api.listChunks(id, 50);
      setChunks(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load chunks");
      setChunks([]);
    } finally {
      setChunksLoading(false);
    }
  }

  const selected = documents.find((d) => d.id === selectedId) ?? null;
  const examName = (id: string) =>
    exams.find((e) => e.id === id)?.code ?? id.slice(0, 8);

  return (
    <div>
      <PageHeader
        eyebrow="Ingestion"
        title="Documents"
        description="Upload PDFs, queue knowledge-base processing, and inspect semantic chunks with LLM-extracted metadata."
        actions={
          <Button variant="secondary" onClick={() => void load()}>
            Refresh
          </Button>
        }
      />

      {error ? (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <Panel>
          <h2 className="font-display text-xl text-stone-50">Upload PDF</h2>
          <form className="mt-4 space-y-4" onSubmit={onUpload}>
            <Field label="Exam">
              <select
                className={inputClass}
                value={examId}
                onChange={(e) => setExamId(e.target.value)}
                required
              >
                {exams.length === 0 ? (
                  <option value="">No exams — create one first</option>
                ) : null}
                {exams.map((exam) => (
                  <option key={exam.id} value={exam.id}>
                    {exam.code} — {exam.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Title">
              <input
                className={inputClass}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                placeholder="Banking Awareness Vol. 1"
              />
            </Field>
            <Field label="Type">
              <select
                className={inputClass}
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value as DocumentType)}
              >
                {DOC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="PDF file" hint="Max size configured on the API (default 50MB)">
              <input
                className={`${inputClass} file:mr-3 file:rounded-lg file:border-0 file:bg-teal-400/20 file:px-3 file:py-1.5 file:text-sm file:text-teal-200`}
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </Field>
            <Button type="submit" disabled={uploading || !file || !examId}>
              {uploading ? "Uploading…" : "Upload"}
            </Button>
          </form>
        </Panel>

        <Panel>
          <h2 className="font-display text-xl text-stone-50">Library</h2>
          <div className="mt-4">
            {loading ? <LoadingBlock /> : null}
            {!loading && documents.length === 0 ? (
              <EmptyState
                title="Empty library"
                description="Upload a study PDF to begin extraction and chunking."
              />
            ) : null}
            {!loading && documents.length > 0 ? (
              <ul className="max-h-[28rem] space-y-3 overflow-y-auto pr-1">
                {documents.map((doc) => (
                  <li
                    key={doc.id}
                    className="rounded-xl border border-white/6 bg-white/[0.03] px-4 py-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-stone-100">{doc.title}</p>
                        <p className="mt-1 text-xs text-stone-500">
                          {examName(doc.exam_id)} · {doc.document_type.replaceAll("_", " ")} ·{" "}
                          {formatBytes(doc.file_size_bytes)} · {doc.chunk_count} chunks
                        </p>
                        <p className="mt-1 text-xs text-stone-600">
                          {formatDate(doc.created_at)}
                          {doc.error_message ? ` · ${doc.error_message}` : ""}
                        </p>
                      </div>
                      <Badge className={statusTone(doc.status)}>{doc.status}</Badge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(doc.status === "UPLOADED" || doc.status === "FAILED") && (
                        <Button
                          variant="secondary"
                          onClick={() => void onProcess(doc.id)}
                          disabled={processingId === doc.id}
                        >
                          {processingId === doc.id ? "Queuing…" : "Process"}
                        </Button>
                      )}
                      <Button variant="ghost" onClick={() => void openChunks(doc.id)}>
                        View chunks
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </Panel>
      </div>

      {selectedId ? (
        <Panel className="mt-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-xl text-stone-50">
                Chunks{selected ? ` — ${selected.title}` : ""}
              </h2>
              <p className="mt-1 text-sm text-stone-500">
                Metadata is extracted per chunk by the configured LLM.
              </p>
            </div>
            <Button variant="ghost" onClick={() => setSelectedId(null)}>
              Close
            </Button>
          </div>
          {chunksLoading ? <LoadingBlock label="Loading chunks…" /> : null}
          {!chunksLoading && chunks.length === 0 ? (
            <EmptyState
              title="No chunks"
              description="Process the document first to generate semantic chunks."
            />
          ) : null}
          {!chunksLoading && chunks.length > 0 ? (
            <ul className="space-y-4">
              {chunks.map((chunk) => {
                const meta = chunk.metadata as Record<string, unknown>;
                return (
                  <li
                    key={chunk.id}
                    className="rounded-xl border border-white/6 bg-[#08141a] px-4 py-4"
                  >
                    <div className="mb-2 flex flex-wrap gap-2 text-xs text-stone-500">
                      <span>Page {chunk.page_number}</span>
                      <span>·</span>
                      <span>Chunk #{chunk.chunk_index}</span>
                      {typeof meta.topic === "string" && meta.topic ? (
                        <>
                          <span>·</span>
                          <span className="text-teal-300/80">{meta.topic}</span>
                        </>
                      ) : null}
                    </div>
                    {chunk.summary ? (
                      <p className="mb-2 text-sm text-stone-300">{chunk.summary}</p>
                    ) : null}
                    <p className="line-clamp-5 whitespace-pre-wrap text-sm leading-relaxed text-stone-400">
                      {chunk.content}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}
