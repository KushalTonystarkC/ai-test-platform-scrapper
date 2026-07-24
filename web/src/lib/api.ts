import type {
  ClearQuestionsResponse,
  Document,
  DocumentChunkListResponse,
  DocumentListResponse,
  DocumentProcessResponse,
  DocumentType,
  Exam,
  GenerateQuestionRequest,
  GenerateQuestionResponse,
  GenerateStreamEvent,
  HealthResponse,
  Question,
  QuestionListResponse,
  SearchMode,
  SearchResponse,
} from "./types";
import { ApiError } from "./types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

function parseSseChunk(chunk: string): GenerateStreamEvent | null {
  const lines = chunk.split("\n");
  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    return { event, ...data } as GenerateStreamEvent;
  } catch {
    return null;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown;
  let message = res.statusText || "Request failed";
  try {
    detail = await res.json();
    if (detail && typeof detail === "object") {
      if ("error" in detail) {
        const error = (detail as { error?: unknown }).error;
        if (error && typeof error === "object" && "message" in error) {
          const value = (error as { message: unknown }).message;
          message = typeof value === "string" ? value : JSON.stringify(value);
        }
      } else if ("detail" in detail) {
        const value = (detail as { detail: unknown }).detail;
        message = typeof value === "string" ? value : JSON.stringify(value);
      }
    }
  } catch {
    /* ignore */
  }
  return new ApiError(res.status, message, detail);
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(url), {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
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

  updateExam: (
    id: string,
    body: {
      name?: string;
      description?: string;
      is_active?: boolean;
    },
  ) =>
    getJson<Exam>(`/api/v1/exams/${id}`, {
      method: "PATCH",
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

  generateQuestionsStream: async function* (
    body: GenerateQuestionRequest,
  ): AsyncGenerator<GenerateStreamEvent, void, unknown> {
    const res = await fetch(apiUrl("/api/v1/questions/generate/stream"), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!res.ok) throw await parseError(res);
    if (!res.body) throw new ApiError(502, "Empty stream response");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";
      for (const chunk of chunks) {
        const event = parseSseChunk(chunk);
        if (event) yield event;
      }
    }
    if (buffer.trim()) {
      const event = parseSseChunk(buffer);
      if (event) yield event;
    }
  },

  deleteQuestion: (id: string) =>
    getJson<void>(`/api/v1/questions/${id}`, { method: "DELETE" }),

  clearQuestions: (examId?: string) =>
    getJson<ClearQuestionsResponse>(
      `/api/v1/questions${qs({ exam_id: examId })}`,
      { method: "DELETE" },
    ),
};
