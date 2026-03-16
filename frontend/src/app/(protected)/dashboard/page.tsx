"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { VideoResponse, AnalysisSessionResponse } from "@/lib/types";
import { VideoCard } from "@/components/video/video-card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Card, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";

export default function DashboardPage() {
  const [videos, setVideos] = useState<VideoResponse[]>([]);
  const [sessions, setSessions] = useState<AnalysisSessionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());

  const fetchData = useCallback(() => {
    Promise.all([api.listVideos(), api.listSessions()])
      .then(([v, s]) => { setVideos(v); setSessions(s); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleting((prev) => new Set(prev).add(sessionId));
    try {
      await api.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch {
      // ignore
    } finally {
      setDeleting((prev) => {
        const next = new Set(prev);
        next.delete(sessionId);
        return next;
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <Link href="/upload">
          <Button>Upload Video</Button>
        </Link>
      </div>

      {/* Recent Sessions */}
      {sessions.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-white mb-3">Recent Analysis</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {sessions.slice(0, 6).map((s) => (
              <Link key={s.id} href={`/sessions/${s.id}`}>
                <Card className="hover:border-zinc-600 transition-colors cursor-pointer relative group">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm text-zinc-400 font-mono">
                      {new Date(s.created_at).toLocaleDateString()}
                    </p>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={s.status} />
                      {(s.status === "failed" || s.status === "queued" || s.status === "completed") && (
                        <button
                          onClick={(e) => handleDeleteSession(s.id, e)}
                          disabled={deleting.has(s.id)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-zinc-500 hover:text-red-400 text-xs px-1.5 py-0.5 rounded border border-zinc-700 hover:border-red-800"
                          title="Remove"
                        >
                          {deleting.has(s.id) ? "..." : "\u2715"}
                        </button>
                      )}
                    </div>
                  </div>
                  {s.status === "completed" && (
                    <div className="flex items-center gap-4 text-sm">
                      <span className="text-white">{s.total_strikes ?? 0} strikes</span>
                      <span className="text-zinc-400">
                        Guard: {s.guard_score?.toFixed(0) ?? "--"}%
                      </span>
                    </div>
                  )}
                  {s.status === "failed" && (
                    <p className="text-xs text-red-400 mt-1">Analysis failed</p>
                  )}
                  {s.status === "queued" && (
                    <p className="text-xs text-yellow-400 mt-1">Stuck in queue</p>
                  )}
                </Card>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Videos */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-3">Your Videos</h2>
        {videos.length === 0 ? (
          <Card className="text-center py-12">
            <CardTitle>No videos yet</CardTitle>
            <p className="text-sm text-zinc-400 mt-2">Upload your first fight clip to get started.</p>
            <Link href="/upload">
              <Button className="mt-4">Upload Video</Button>
            </Link>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {videos.map((v) => (
              <VideoCard key={v.id} video={v} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
