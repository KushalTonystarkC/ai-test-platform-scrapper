export type DocumentType = "BOOK" | "PREVIOUS_YEAR_PAPER" | "SYLLABUS";
export type DocumentStatus =
  | "UPLOADED"
  | "PROCESSING"
  | "PROCESSED"
  | "FAILED";
export type SearchMode = "keyword" | "semantic" | "hybrid";
export type Difficulty = "easy" | "medium" | "hard";

export interface Exam {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Document {
  id: string;
  exam_id: string;
  title: string;
  document_type: DocumentType;
  status: DocumentStatus;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  page_count: number | null;
  chunk_count: number;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentChunk {
  id: string;
  document_id: string;
  page_number: number;
  chunk_index: number;
  content: string;
  summary: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface DocumentChunkListResponse {
  items: DocumentChunk[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentProcessResponse {
  document_id: string;
  status: DocumentStatus;
  message: string;
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  page_number: number;
  chunk_index: number;
  content: string;
  summary: string | null;
  metadata: Record<string, unknown>;
  score: number;
  keyword_score: number | null;
  semantic_score: number | null;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  items: SearchHit[];
  total: number;
}

export interface Question {
  id: string;
  exam_id: string;
  subject_id: string | null;
  stem: string;
  options: string[];
  correct_index: number;
  explanation: string;
  subject: string;
  topic: string;
  difficulty: string;
  source_chunk_ids: string[];
  document_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface QuestionListResponse {
  items: Question[];
  total: number;
  limit: number;
  offset: number;
}

export interface GenerateQuestionRequest {
  exam_id: string;
  topic?: string | null;
  count?: number;
  difficulty?: Difficulty | null;
  document_id?: string | null;
  subject?: string | null;
}

export interface GenerateQuestionResponse {
  exam_id: string;
  topic: string | null;
  mode: "topic" | "full_syllabus";
  requested_count: number;
  generated_count: number;
  context_used: number;
  items: Question[];
}

export type GenerateStreamEvent =
  | {
      event: "started";
      exam_id: string;
      topic: string | null;
      mode: "topic" | "full_syllabus";
      requested_count: number;
      context_used: number;
    }
  | { event: "slot_started"; index: number; total: number }
  | {
      event: "attempt_failed";
      index: number;
      attempt: number;
      error: string;
      stem?: string;
    }
  | { event: "slot_exhausted"; index: number; error: string }
  | { event: "question"; index: number; item: Question }
  | {
      event: "done";
      exam_id: string;
      topic: string | null;
      mode: "topic" | "full_syllabus";
      requested_count: number;
      generated_count: number;
      context_used: number;
    }
  | { event: "error"; error: string; code?: string | null };

export interface ClearQuestionsResponse {
  deleted_count: number;
  exam_id: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  question_generate_max_count?: number;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
