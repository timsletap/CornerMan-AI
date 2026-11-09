"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clipDurationMs, summarizeStrikes } from "@/lib/fight-stats";
import { formatClock, formatDate } from "@/lib/format";
import { strikeMeta } from "@/lib/strike-meta";
import type { AnalysisSessionDetailResponse, ProgressResponse } from "@/lib/types";
import { VideoPlayer, seekTo } from "@/components/video/video-player";
import { AnalysisProgress } from "@/components/analysis/analysis-progress";
import { ErrorFlagList } from "@/components/analysis/error-flag-list";
import { FightTimeline } from "@/components/analysis/fight-timeline";
import { GuardRing } from "@/components/analysis/guard-ring";
import { StrikeBreakdown } from "@/components/analysis/strike-breakdown";
import { StrikeTimeline } from "@/components/analysis/strike-timeline";
import { CoachFeedbackPanel } from "@/components/coaching/coach-feedback";
import { DrillCard } from "@/components/coaching/drill-card";
import { FeedbackButtons } from "@/components/coaching/feedback-buttons";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { ErrorNote, LoadingBlock } from "@/components/ui/spinner";
import { useSignedMediaUrl } from "@/lib/hooks/use-signed-media-url";
import { subscribeToSessionEvents } from "@/lib/session-events";

function Stat({ label, value, unit, tone = "text-chalk" }: {
  label: string;
  value: string;
  unit?: string;
  tone?: string;
}) {
  return (
    <div className="bg-panel p-4 sm:p-5">
      <p className="eyebrow">{label}</p>
      <p className={`display mt-2 text-4xl sm:text-5xl ${tone}`}>
        {value}
        {unit && <span className="ml-1 text-xl text-mute">{unit}</span>}
      </p>
    </div>
  );
}

export default function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();
  const [session, setSession] = useState<AnalysisSessionDetailResponse | null>(null);
  const [clipName, setClipName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState("");
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [showAnnotated, setShowAnnotated] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const originalStream = useSignedMediaUrl("video", session?.video_id ?? null);
  const annotatedStream = useSignedMediaUrl(
    "annotated",
    session?.annotated_video_path ? session.id : null,
  );

  const fetchSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await api.getSession(sessionId);
      setSession(data);
      if (data.status === "completed" || data.status === "failed") {
        setProgress(null);
      }
    } catch {
      // leave `session` as is; a missing session renders the not-found state
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  // The clip's file name makes a better title than an id; it is optional
  const videoId = session?.video_id;
  useEffect(() => {
    if (!videoId) return;
    api
      .getVideo(videoId)
      .then((v) => setClipName(v.original_filename))
      .catch(() => {});
  }, [videoId]);

  // Live progress over server-sent events while the analysis runs (no polling)
  const isRunning = session?.status === "queued" || session?.status === "processing";
  useEffect(() => {
    if (!sessionId || !isRunning) return;
    return subscribeToSessionEvents(sessionId, {
      onProgress: setProgress,
      onFinished: () => {
        setProgress(null);
        fetchSession();
      },
    });
  }, [sessionId, isRunning, fetchSession]);

  if (loading) return <LoadingBlock />;

  if (!session) {
    return (
      <div className="py-24 text-center">
        <h1 className="display text-5xl text-chalk">Breakdown not found</h1>
        <p className="mt-3 text-mute">It may have been deleted.</p>
        <ButtonLink href="/dashboard" variant="outline" className="mt-6">
          Back to camp
        </ButtonLink>
      </div>
    );
  }

  if (session.status === "queued" || session.status === "processing") {
    return (
      <div className="mx-auto max-w-4xl py-6">
        <AnalysisProgress progress={progress} />
      </div>
    );
  }

  if (session.status === "failed") {
    const handleDelete = async () => {
      setActionError("");
      try {
        await api.deleteSession(session.id);
        router.push("/dashboard");
      } catch {
        setActionError("Couldn't remove it. Try again.");
      }
    };
    const handleRetry = async () => {
      setActionError("");
      try {
        await api.deleteSession(session.id);
        const next = await api.triggerAnalysis(session.video_id);
        router.push(`/sessions/${next.id}`);
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Couldn't restart the breakdown.");
      }
    };
    return (
      <div className="mx-auto max-w-xl py-20 text-center">
        <p className="eyebrow text-blood">No contest</p>
        <h1 className="display mt-2 text-5xl text-chalk">This breakdown didn&apos;t finish</h1>
        <p className="mt-4 text-mute">
          Something went wrong while analyzing the clip. Retrying often works. If it keeps
          failing, try a clip where one fighter stays fully in frame.
        </p>
        {actionError && <div className="mt-5 text-left"><ErrorNote>{actionError}</ErrorNote></div>}
        <div className="mt-8 flex justify-center gap-3">
          <Button onClick={handleRetry}>Run it again</Button>
          <Button variant="outline" onClick={handleDelete}>
            Remove
          </Button>
        </div>
      </div>
    );
  }

  const hasAnnotated = Boolean(session.annotated_video_path);
  const activeStream = showAnnotated && hasAnnotated ? annotatedStream : originalStream;
  const metrics = session.vision_json?.metrics;
  const summary = summarizeStrikes(session.strike_events);
  const activeFlags = session.error_flags.filter((f) => !f.user_disputed).length;
  const durationMs = clipDurationMs(session.vision_json?.video_metadata?.duration_seconds, [
    ...session.strike_events.map((s) => s.timestamp_ms),
    ...session.error_flags.map((f) => f.timestamp_ms),
  ]);
  const seek = (ms: number) => {
    seekTo(videoRef, ms);
    setCurrentTimeMs(ms);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow mb-2 text-blood">
            Fight report · {formatDate(session.created_at)}
          </p>
          <h1 className="display truncate text-5xl text-chalk sm:text-6xl">
            {clipName ?? "Round breakdown"}
          </h1>
        </div>
        <ButtonLink href={`/videos/${session.video_id}`} variant="outline" size="sm">
          Open clip
        </ButtonLink>
      </header>

      {/* Scorecard */}
      <section
        aria-label="Scorecard"
        className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-line bg-line lg:grid-cols-[auto_1fr]"
      >
        <div className="flex items-center gap-5 bg-panel p-5">
          <GuardRing score={session.guard_score} />
          <div className="max-w-[13rem]">
            <p className="eyebrow">Guard score</p>
            <p className="mt-2 text-sm leading-relaxed text-mute">
              Share of your punches thrown with the other hand still protecting your chin.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-4">
          <Stat label="Strikes" value={(session.total_strikes ?? summary.total).toString()} />
          <Stat
            label="Per minute"
            value={metrics?.strikes_per_minute?.toFixed(1) ?? "--"}
          />
          <Stat
            label="Avg hand speed"
            value={session.avg_velocity?.toFixed(1) ?? "--"}
            unit="u/s"
          />
          <Stat
            label="Flags"
            value={activeFlags.toString()}
            tone={activeFlags > 0 ? "text-blood" : "text-go"}
          />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.25fr_1fr]">
        {/* Film */}
        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          {hasAnnotated && (
            <div className="inline-flex border border-line-2" role="group" aria-label="Video view">
              {[
                { on: true, label: "Tracking overlay" },
                { on: false, label: "Original" },
              ].map((view) => (
                <button
                  key={view.label}
                  onClick={() => setShowAnnotated(view.on)}
                  aria-pressed={showAnnotated === view.on}
                  className={`cursor-pointer px-4 py-1.5 font-display text-sm font-bold uppercase tracking-wider transition-colors
                    ${showAnnotated === view.on ? "bg-chalk text-canvas" : "text-mute hover:text-chalk"}`}
                >
                  {view.label}
                </button>
              ))}
            </div>
          )}

          <VideoPlayer
            src={activeStream.url}
            onSrcError={activeStream.refreshIfExpired}
            videoRef={videoRef}
            onTimeUpdate={setCurrentTimeMs}
          />

          <Card>
            <div className="mb-4 flex items-center justify-between">
              <CardTitle>Round timeline</CardTitle>
              <span className="font-mono text-xs text-mute">
                {formatClock(currentTimeMs)} / {formatClock(durationMs)}
              </span>
            </div>
            <FightTimeline
              strikes={session.strike_events}
              errors={session.error_flags}
              durationMs={durationMs}
              currentTimeMs={currentTimeMs}
              onSeek={seek}
            />
            {summary.fastest && (
              <p className="mt-4 border-t border-line pt-3 text-sm text-mute">
                Fastest punch:{" "}
                <button
                  onClick={() => seek(summary.fastest!.timestamp_ms)}
                  className="cursor-pointer font-medium text-chalk underline decoration-blood underline-offset-4 hover:text-blood"
                >
                  {strikeMeta(summary.fastest.strike_type).label.toLowerCase()} at{" "}
                  {formatClock(summary.fastest.timestamp_ms)}
                </button>{" "}
                ({summary.fastest.velocity?.toFixed(1)} u/s)
              </p>
            )}
          </Card>
        </div>

        {/* Analysis */}
        <div className="space-y-6">
          <CoachFeedbackPanel rawFeedback={session.coach_feedback} />
          <FeedbackButtons sessionId={session.id} />

          <Card>
            <CardTitle className="mb-4">Punch selection</CardTitle>
            <StrikeBreakdown summary={summary} />
          </Card>

          <Card accent={activeFlags > 0 ? "blood" : "none"}>
            <CardTitle className="mb-3">Flags</CardTitle>
            <ErrorFlagList
              errors={session.error_flags}
              sessionId={session.id}
              currentTimeMs={currentTimeMs}
              onSeek={seek}
            />
          </Card>

          <Card>
            <div className="mb-3 flex items-end justify-between">
              <CardTitle>Strike log</CardTitle>
              <span className="eyebrow">Speed in u/s</span>
            </div>
            <StrikeTimeline
              strikes={session.strike_events}
              currentTimeMs={currentTimeMs}
              onSeek={seek}
            />
          </Card>

          {session.drill_recommendations.length > 0 && (
            <section>
              <h2 className="display mb-3 text-3xl text-chalk">Homework</h2>
              <div className="space-y-3">
                {session.drill_recommendations.map((rec, i) => (
                  <DrillCard key={rec.id} rec={rec} index={i} />
                ))}
              </div>
            </section>
          )}

          <p className="text-xs leading-relaxed text-dim">
            Speeds are in frame heights per second (u/s), so compare them within a clip, not
            across camera setups. Strike calls come from pose tracking and can be wrong;
            dispute any flag that doesn&apos;t match what you see.
          </p>
        </div>
      </div>
    </div>
  );
}
