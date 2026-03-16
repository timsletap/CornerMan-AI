"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { AnalysisSessionDetailResponse } from "@/lib/types";
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

export default function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<AnalysisSessionDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
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
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  // Poll while processing
  useEffect(() => {
    if (session && (session.status === "queued" || session.status === "processing")) {
      pollRef.current = setInterval(fetchSession, 3000);
      return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }
  }, [session?.status, fetchSession]);

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

  // Still processing
  if (session.status === "queued" || session.status === "processing") {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <Spinner size="lg" />
        <StatusBadge status={session.status} />
        <p className="text-zinc-400">
          {session.status === "queued"
            ? "Your analysis is queued. Hang tight..."
            : "Analyzing your footage. This may take a minute..."}
        </p>
      </div>
    );
  }

  if (session.status === "failed") {
    return (
      <div className="text-center py-20">
        <StatusBadge status="failed" />
        <p className="text-zinc-400 mt-4">Analysis failed. Please try again with a different video.</p>
      </div>
    );
  }

  const streamUrl = api.getVideoStreamUrl(session.video_id);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Analysis Results</h1>
        <StatusBadge status={session.status} />
      </div>

      {/* Metrics */}
      <MetricsPanel
        totalStrikes={session.total_strikes}
        avgVelocity={session.avg_velocity}
        guardScore={session.guard_score}
      />

      {/* Main layout: video + panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Video */}
        <div className="lg:sticky lg:top-20 lg:self-start space-y-4">
          <VideoPlayer
            src={streamUrl}
            videoRef={videoRef}
            onTimeUpdate={setCurrentTimeMs}
          />
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
              <h3 className="text-lg font-semibold text-white mb-3">Recommended Drills</h3>
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
