export type SuggestedDepth = 'deep' | 'skim' | 'file';

export type TriageStatus = 'pending' | 'kept' | 'dismissed' | 'auto_rejected' | 'deep' | 'filed';

/** Mirrors the backend `PaperOut` schema (GET /api/triage/queue). */
export interface Paper {
  id: number;
  title: string;
  authors: string[];
  source_type: string;
  url: string;
  abstract: string | null;
  /** ISO 8601 UTC timestamp of when the pipeline discovered the paper. */
  discovered_at: string;
  llm_interest_score: number | null;
  /** The "why this surfaced" reason shown on the card. */
  llm_reasoning: string | null;
  llm_tags: string[];
  /** Discovery signal(s) that surfaced the paper: keyword | topic | author | citation | institution. */
  surfaced_by: string[];
  suggested_depth: SuggestedDepth | null;
  status: TriageStatus;
  /** ISO 8601 UTC timestamp of the triage decision; null while pending. */
  decided_at: string | null;
  // --- Routing outcomes (populated as papers are routed to Zotero/Obsidian) ---
  zotero_key: string | null;
  zotero_error: string | null;
  obsidian_path: string | null;
  obsidian_error: string | null;
  /** reMarkable via Drive. Optional: an older backend omits them. */
  drive_file_id?: string | null;
  drive_error?: string | null;
  /** No open-access PDF was found, so nothing was sent to the tablet. */
  pdf_unavailable?: boolean;
  /** How many routing attempts have been made (initial + retries). */
  routing_attempts: number;
  /** ISO 8601 UTC time of the next scheduled retry; null when done or given up. */
  next_retry_at: string | null;
}

/** The decisions a paper can be routed to (the `pending` status is the absence of a decision). */
export type Decision = 'kept' | 'dismissed';
