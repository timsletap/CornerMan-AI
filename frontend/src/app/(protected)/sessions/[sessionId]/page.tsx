"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type {
  AnalysisSessionDetailResponse,
  ProgressResponse,
} from "@/lib/types";
import { VideoPlayer, seekTo } from "@/components/video/video-player";
import { MetricsPanel } from "@/components/analysis/metrics-panel";
import { StrikeTimeline } from "@/components/analysis/strike-timeline";
import { ErrorFlagList } from "@/components/analysis/error-flag-list";
import { CoachFeedbackPanel } from "@/components/coaching/coach-feedback";
import { FeedbackButtons } from "@/components/coaching/feedback-buttons";
import { DrillCard } from "@/components/coaching/drill-card";
import { Card, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { StatusBadge } from "@/components/ui/badge";
import { AnalysisProgress } from "@/components/analysis/analysis-progress";
import { useSignedMediaUrl } from "@/lib/hooks/use-signed-media-url";

export default function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();
  const [session, setSession] =
    useState<AnalysisSessionDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [showAnnotated, setShowAnnotated] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const originalStream = useSignedMediaUrl("video", session?.video_id ?? null);
  const annotatedStream = useSignedMediaUrl(
    "annotated",
    session?.annotated_video_path ? session.id : null,
  );
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await api.getSession(sessionId);
      setSession(data);
      if (data.status === "completed" || data.status === "failed") {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        setProgress(null);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const fetchProgress = useCallback(async () => {
    if (!sessionId) return;
    try {
      const p = await api.getSessionProgress(sessionId);
      setProgress(p);
    } catch {
      // ignore
    }
  }, [sessionId]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  // Poll while processing
  useEffect(() => {
    if (
      session &&
      (session.status === "queued" || session.status === "processing")
    ) {
      // Fetch progress immediately
      fetchProgress();
      pollRef.current = setInterval(() => {
        fetchSession();
        fetchProgress();
      }, 1500);
      return () => {
        if (pollRef.current) clearInterval(pollRef.current);
      };
    }
  }, [session?.status, fetchSession, fetchProgress]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner />
      </div>
    );
  }

  if (!session) {
    return <p className="text-zinc-400">Session not found.</p>;
  }

  // Still processing — show rich progress view
  if (session.status === "queued" || session.status === "processing") {
    return (
      <div className="max-w-2xl mx-auto py-12 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-white">Analyzing Video</h1>
          <StatusBadge status={session.status} />
        </div>
        <AnalysisProgress progress={progress} />
      </div>
    );
  }

  if (session.status === "failed") {
    const handleDelete = async () => {
      await api.deleteSession(session.id);
      router.push("/dashboard");
    };
    const handleRetry = async () => {
      await api.deleteSession(session.id);
      const newSession = await api.triggerAnalysis(session.video_id);
      router.push(`/sessions/${newSession.id}`);
    };
    return (
      <div className="text-center py-20 space-y-4">
        <StatusBadge status="failed" />
        <p className="text-zinc-400">
          Analysis failed. Please try again with a different video.
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={handleRetry}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors"
          >
            Retry Analysis
          </button>
          <button
            onClick={handleDelete}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors"
          >
            Remove
          </button>
        </div>
      </div>
    );
  }

  const hasAnnotated = Boolean(session.annotated_video_path);
  const activeStream =
    showAnnotated && hasAnnotated ? annotatedStream : originalStream;

  // Compute extra stats from vision_json
  const vj = session.vision_json;
  const strikesPerMin = vj?.metrics?.strikes_per_minute;
  const framesAnalyzed = vj?.frames_analyzed;
  const errorCounts = vj?.metrics?.error_counts;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Analysis Results</h1>
        <StatusBadge status={session.status} />
      </div>

      {/* Extended Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          label="Total Strikes"
          value={session.total_strikes?.toString() || "--"}
          color="text-white"
        />
        <MetricCard
          label="Avg Velocity"
          value={session.avg_velocity?.toFixed(1) || "--"}
          unit="u/s"
          color="text-blue-400"
        />
        <MetricCard
          label="Guard Score"
          value={session.guard_score?.toFixed(0) || "--"}
          unit="%"
          color={
            session.guard_score !== null
              ? session.guard_score >= 80
                ? "text-green-400"
                : session.guard_score >= 50
                  ? "text-yellow-400"
                  : "text-red-400"
              : "text-zinc-400"
          }
        />
        <MetricCard
          label="Strikes/Min"
          value={strikesPerMin?.toFixed(1) || "--"}
          color="text-cyan-400"
        />
        <MetricCard
          label="Frames Tracked"
          value={framesAnalyzed?.toString() || "--"}
          color="text-purple-400"
        />
        <MetricCard
          label="Errors Found"
          value={session.error_flags.length.toString()}
          color={
            session.error_flags.length > 0 ? "text-red-400" : "text-green-400"
          }
        />
      </div>

      {/* Error breakdown bar */}
      {errorCounts && (
        <div className="flex items-center gap-4 text-xs text-zinc-400">
          <span className="uppercase tracking-wider">Error Breakdown:</span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            Dropped Guard: {errorCounts.dropped_guard || 0}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-orange-500" />
            Telegraph: {errorCounts.chicken_wing || 0}
          </span>
        </div>
      )}

      {/* Main layout: video + panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Video */}
        <div className="lg:sticky lg:top-20 lg:self-start space-y-3">
          {/* Video toggle */}
          {hasAnnotated && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowAnnotated(true)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  showAnnotated
                    ? "bg-red-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                AI Tracking View
              </button>
              <button
                onClick={() => setShowAnnotated(false)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  !showAnnotated
                    ? "bg-red-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                Original Video
              </button>
            </div>
          )}

          <VideoPlayer
            src={activeStream.url}
            onSrcError={activeStream.refreshIfExpired}
            videoRef={videoRef}
            onTimeUpdate={setCurrentTimeMs}
          />

          {showAnnotated && hasAnnotated && (
            <p className="text-[10px] text-zinc-600 text-center">
              Skeleton tracking, strike detection & guard analysis overlay
            </p>
          )}
        </div>

        {/* Right: Scrollable panels */}
        <div className="space-y-6">
          {/* Coaching Feedback */}
          <CoachFeedbackPanel rawFeedback={session.coach_feedback} />
          <FeedbackButtons sessionId={session.id} />

          {/* Strike Timeline */}
          <Card>
            <CardTitle>Strike Timeline</CardTitle>
            <div className="mt-3">
              <StrikeTimeline
                strikes={session.strike_events}
                currentTimeMs={currentTimeMs}
                onSeek={(ms) => seekTo(videoRef, ms)}
              />
            </div>
          </Card>

          {/* Error Flags */}
          <Card>
            <CardTitle>Error Flags</CardTitle>
            <div className="mt-3">
              <ErrorFlagList
                errors={session.error_flags}
                sessionId={session.id}
                currentTimeMs={currentTimeMs}
                onSeek={(ms) => seekTo(videoRef, ms)}
              />
            </div>
          </Card>

          {/* Drill Recommendations */}
          {session.drill_recommendations.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">
                Recommended Drills
              </h3>
              <div className="space-y-3">
                {session.drill_recommendations.map((rec) => (
                  <DrillCard key={rec.id} rec={rec} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  unit,
  color,
}: {
  label: string;
  value: string;
  unit?: string;
  color: string;
}) {
  return (
    <Card className="text-center py-4 px-3">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wider">
        {label}
      </p>
      <p className={`text-2xl font-bold mt-1 ${color}`}>
        {value}
        {unit && <span className="text-sm ml-0.5">{unit}</span>}
      </p>
    </Card>
  );
}
