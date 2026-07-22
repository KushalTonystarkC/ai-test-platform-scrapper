import type { DocumentStatus } from "./types";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function statusTone(status: DocumentStatus): string {
  switch (status) {
    case "PROCESSED":
      return "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30";
    case "PROCESSING":
      return "bg-sky-500/15 text-sky-300 ring-sky-500/30";
    case "FAILED":
      return "bg-rose-500/15 text-rose-300 ring-rose-500/30";
    default:
      return "bg-amber-500/15 text-amber-200 ring-amber-500/30";
  }
}

export function difficultyTone(d: string): string {
  switch (d.toLowerCase()) {
    case "easy":
      return "bg-emerald-500/15 text-emerald-300";
    case "hard":
      return "bg-rose-500/15 text-rose-300";
    default:
      return "bg-amber-500/15 text-amber-200";
  }
}

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
