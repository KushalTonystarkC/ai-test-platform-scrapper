"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Exam } from "@/lib/types";
import { ApiError } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Field,
  LoadingBlock,
  PageHeader,
  Panel,
  inputClass,
} from "@/components/ui";

export default function ExamsPage() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setExams(await api.listExams());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load exams");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.createExam({
        code: code.trim().toUpperCase(),
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setCode("");
      setName("");
      setDescription("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create exam");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Catalog"
        title="Exams"
        description="Each exam scopes documents, search, and generated questions. Seed scripts create IBPS-style codes; you can add more here."
      />

      {error ? (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Panel>
          <h2 className="font-display text-xl text-stone-50">Add exam</h2>
          <form className="mt-4 space-y-4" onSubmit={onCreate}>
            <Field label="Code" hint="e.g. IBPS_PO">
              <input
                className={inputClass}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                maxLength={64}
                placeholder="IBPS_PO"
              />
            </Field>
            <Field label="Name">
              <input
                className={inputClass}
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={255}
                placeholder="IBPS Probationary Officer"
              />
            </Field>
            <Field label="Description">
              <textarea
                className={`${inputClass} min-h-24 resize-y`}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional notes for this catalog"
              />
            </Field>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Create exam"}
            </Button>
          </form>
        </Panel>

        <Panel>
          <h2 className="font-display text-xl text-stone-50">All exams</h2>
          <div className="mt-4">
            {loading ? <LoadingBlock /> : null}
            {!loading && exams.length === 0 ? (
              <EmptyState
                title="No exams"
                description="Create an exam or run python -m scripts.seed_exams on the backend."
              />
            ) : null}
            {!loading && exams.length > 0 ? (
              <ul className="space-y-3">
                {exams.map((exam) => (
                  <li
                    key={exam.id}
                    className="rounded-xl border border-white/6 bg-white/[0.03] px-4 py-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-xs text-teal-300">{exam.code}</p>
                        <p className="mt-1 text-sm font-medium text-stone-100">{exam.name}</p>
                        {exam.description ? (
                          <p className="mt-1 text-sm text-stone-500">{exam.description}</p>
                        ) : null}
                      </div>
                      <span className="text-xs text-stone-500">
                        {exam.is_active ? "Active" : "Inactive"}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-stone-600">
                      Created {formatDate(exam.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}
