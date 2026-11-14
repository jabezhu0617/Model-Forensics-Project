export type Outcome = 'concealed' | 'reported' | 'unresolved';
export interface Counts { concealed: number; reported: number; unresolved: number }
export interface RunSummary {
  id: string; outcome: Outcome; status: string; transcript_hash: string;
  selected: boolean; support: string; excerpt: string; messageCount: number;
}
export interface Segment { text: string; anchors: [number, number][]; label: string; kind: string }
export interface Message { role: string; index: number; segments: Segment[]; exit_code?: number; step?: number }
export interface TemporarySource {
  title: string; model: string; scenario: string; run: string; status: string;
  sourceUrl: string; sourceRevision: string; downloadUrl: string;
  bytes: number; steps: number; reasoningBlocks: number; toolCalls: number;
}
export interface TemporarySummary extends TemporarySource { id: string; messageCount: number }
export interface Highlight { quote: string; note: string; start?: number; start_utf16?: number; source?: string }
export interface Run extends RunSummary {
  experiment: string; text: string; display_messages: Message[];
  submission: Record<string,string> | null; annotation: { reviewer?: string; highlights?: Highlight[]; outcome?: Outcome };
  suggested_highlights: Highlight[]; reasoning_available: boolean;
  temporary?: TemporarySource;
}
export interface InputSection { title: string; html: string }
export interface Experiment {
  id: string; label: string; group: string | null; round: number; sign: '−' | '+' | null;
  title: string; score: number | null; point: number | null; runs: RunSummary[];
  requested: number; counts: Counts; attempts: number; inputs?: InputSection[];
}
export interface Hypothesis { id: string; label: string; title: string; round: number; score: number | null; arms: string[] }
export interface Report { id: string; title: string; content: string }
export interface Dataset {
  version: string; sourceCommit: string; sourceRepository: string; repository: string;
  totalRuns: number; totalExperiments: number; counts: Counts;
  experiments: Experiment[]; hypotheses: Hypothesis[]; reports: Report[];
}
export interface Annotation {
  id: string; run_id: string; transcript_hash: string; quote: string; note: string; reviewer: string;
  outcome: Outcome | null; revision: number; created_at: string; updated_at: string; deleted: number;
}
