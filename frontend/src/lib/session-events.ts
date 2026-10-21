import { api } from "@/lib/api";
import type { ProgressResponse } from "@/lib/types";

/** Payload of `progress` / `done` events from GET /sessions/{id}/events (PLT-07). */
interface ProgressEventData {
  stage: string;
  pct: number;
  message: string;
}

export interface SessionEventHandlers {
  onProgress: (progress: ProgressResponse) => void;
  /** Called once when the analysis completes or fails; the stream is closed by then. */
  onFinished: (outcome: "done" | "failed", message: string) => void;
}

// Wait before re-signing after the server rejects or drops the connection (ms).
const RECONNECT_DELAY_MS = 2_000;

export function toProgress(data: ProgressEventData): ProgressResponse {
  return { step: data.stage, progress: data.pct, detail: data.message };
}

/**
 * Subscribe to live analysis progress over server-sent events. Returns a function that
 * closes the stream.
 *
 * EventSource reconnects on its own after a dropped connection, but a reconnect after
 * the signed URL expires gets a 403 and the browser gives up (readyState CLOSED); in
 * that case we sign a fresh URL and open a new stream.
 */
export function subscribeToSessionEvents(
  sessionId: string,
  handlers: SessionEventHandlers,
): () => void {
  let source: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  const stop = () => {
    stopped = true;
    source?.close();
    if (retryTimer) clearTimeout(retryTimer);
  };

  const scheduleRetry = () => {
    if (!stopped) retryTimer = setTimeout(open, RECONNECT_DELAY_MS);
  };

  async function open() {
    let url: string;
    try {
      ({ url } = await api.signMediaUrl("events", sessionId));
    } catch {
      scheduleRetry();
      return;
    }
    if (stopped) return;

    const es = new EventSource(url);
    source = es;
    es.addEventListener("progress", (e) => {
      handlers.onProgress(toProgress(JSON.parse((e as MessageEvent).data)));
    });
    for (const outcome of ["done", "failed"] as const) {
      es.addEventListener(outcome, (e) => {
        const data = JSON.parse((e as MessageEvent).data) as Partial<ProgressEventData>;
        stop();
        handlers.onFinished(outcome, data.message ?? "");
      });
    }
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        es.close();
        scheduleRetry();
      }
    };
  }

  open();
  return stop;
}
