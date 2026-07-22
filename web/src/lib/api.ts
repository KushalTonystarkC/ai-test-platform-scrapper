import type {
  Document,
  DocumentChunkListResponse,
  DocumentListResponse,
  DocumentProcessResponse,
  DocumentType,
  Exam,
  GenerateQuestionRequest,
  GenerateQuestionResponse,
  HealthResponse,
  Question,
  QuestionListResponse,
  SearchMode,
  SearchResponse,
} from "./types";
import { ApiError } from "./types";

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown;
  let message = res.statusText || "Request failed";
  try {
    detail = await res.json();
    if (
      detail &&
      typeof detail === "object" &&
      "detail" in detail &&
      (detail as { detail: unknown }).detail != null
    ) {
      const d = (detail as { detail: unknown }).detail;
      message = typeof d === "string" ? d : JSON.stringify(d);
    }
  } catch {
    /* ignore */
  }
  return new ApiError(res.status, message, detail);
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => getJson<HealthResponse>("/health"),

  listExams: (activeOnly = false) =>
    getJson<Exam[]>(`/api/v1/exams${qs({ active_only: activeOnly })}`),

  createExam: (body: {
    code: string;
    name: string;
    description?: string;
    is_active?: boolean;
  }) =>
    getJson<Exam>("/api/v1/exams", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  listDocuments: (params?: {
    exam_id?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }) =>
    getJson<DocumentListResponse>(
      `/api/v1/documents${qs({
        exam_id: params?.exam_id,
        status: params?.status,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),

  getDocument: (id: string) => getJson<Document>(`/api/v1/documents/${id}`),

  listChunks: (documentId: string, limit = 50, offset = 0) =>
    getJson<DocumentChunkListResponse>(
      `/api/v1/documents/${documentId}/chunks${qs({ limit, offset })}`,
    ),

  uploadDocument: async (input: {
    file: File;
    exam_id: string;
    title: string;
    document_type: DocumentType;
  }) => {
    const form = new FormData();
    form.append("file", input.file);
    form.append("exam_id", input.exam_id);
    form.append("title", input.title);
    form.append("document_type", input.document_type);
    form.append("metadata", "{}");
    const res = await fetch("/api/v1/documents/upload", {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw await parseError(res);
    return res.json() as Promise<Document>;
  },

  processDocument: (id: string) =>
    getJson<DocumentProcessResponse>(`/api/v1/documents/${id}/process`, {
      method: "POST",
    }),

  search: (params: {
    q: string;
    mode?: SearchMode;
    exam_id?: string;
    document_id?: string;
    limit?: number;
  }) =>
    getJson<SearchResponse>(
      `/api/v1/search${qs({
        q: params.q,
        mode: params.mode ?? "hybrid",
        exam_id: params.exam_id,
        document_id: params.document_id,
        limit: params.limit ?? 10,
      })}`,
    ),

  listQuestions: (params?: {
    exam_id?: string;
    difficulty?: string;
    topic?: string;
    limit?: number;
    offset?: number;
  }) =>
    getJson<QuestionListResponse>(
      `/api/v1/questions${qs({
        exam_id: params?.exam_id,
        difficulty: params?.difficulty,
        topic: params?.topic,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),

  getQuestion: (id: string) => getJson<Question>(`/api/v1/questions/${id}`),

  generateQuestions: (body: GenerateQuestionRequest) =>
    getJson<GenerateQuestionResponse>("/api/v1/questions/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
