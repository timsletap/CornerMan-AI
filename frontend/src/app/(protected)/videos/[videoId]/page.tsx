"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { VideoResponse } from "@/lib/types";
import { VideoPlayer } from "@/components/video/video-player";
import { useSignedMediaUrl } from "@/lib/hooks/use-signed-media-url";
import { Card, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";

export default function VideoDetailPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const router = useRouter();
  const [video, setVideo] = useState<VideoResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const stream = useSignedMediaUrl("video", video?.id ?? null);

  useEffect(() => {
    if (videoId) {
      api.getVideo(videoId).then(setVideo).finally(() => setLoading(false));
    }
  }, [videoId]);

  async function handleAnalyze() {
    if (!videoId) return;
    setAnalyzing(true);
    setError("");
    try {
      const session = await api.triggerAnalysis(videoId);
      router.push(`/sessions/${session.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start analysis");
      setAnalyzing(false);
    }
  }

  async function handleDelete() {
    if (!videoId || !confirm("Delete this video?")) return;
    await api.deleteVideo(videoId);
    router.push("/dashboard");
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner />
      </div>
    );
  }

  if (!video) {
    return <p className="text-zinc-400">Video not found.</p>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">{video.original_filename}</h1>
          <div className="flex items-center gap-3 mt-1">
            <StatusBadge status={video.status} />
            <span className="text-sm text-zinc-400">
              {video.duration_seconds?.toFixed(1)}s
            </span>
            <span className="text-sm text-zinc-500 uppercase">{video.format}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={handleAnalyze}
            disabled={analyzing || video.status === "processing"}
          >
            {analyzing ? "Starting..." : "Analyze"}
          </Button>
          <Button variant="danger" size="sm" onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      <VideoPlayer src={stream.url} onSrcError={stream.refreshIfExpired} />

      <Card>
        <CardTitle>Video Details</CardTitle>
        <div className="grid grid-cols-2 gap-4 mt-3 text-sm">
          <div>
            <span className="text-zinc-500">Duration</span>
            <p className="text-white">{video.duration_seconds?.toFixed(1) ?? "--"}s</p>
          </div>
          <div>
            <span className="text-zinc-500">Size</span>
            <p className="text-white">{(video.file_size_bytes / 1024 / 1024).toFixed(1)} MB</p>
          </div>
          <div>
            <span className="text-zinc-500">Format</span>
            <p className="text-white uppercase">{video.format}</p>
          </div>
          <div>
            <span className="text-zinc-500">Uploaded</span>
            <p className="text-white">{new Date(video.created_at).toLocaleString()}</p>
          </div>
        </div>
      </Card>
    </div>
  );
}
