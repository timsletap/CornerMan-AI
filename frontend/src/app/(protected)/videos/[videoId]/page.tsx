"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";
import type { VideoResponse } from "@/lib/types";
import { VideoPlayer } from "@/components/video/video-player";
import { useSignedMediaUrl } from "@/lib/hooks/use-signed-media-url";
import { Button, ButtonLink } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { BoltIcon } from "@/components/ui/icons";
import { ErrorNote, LoadingBlock } from "@/components/ui/spinner";

export default function VideoDetailPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const router = useRouter();
  const [video, setVideo] = useState<VideoResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState("");
  const stream = useSignedMediaUrl("video", video?.id ?? null);

  useEffect(() => {
    if (!videoId) return;
    api
      .getVideo(videoId)
      .then(setVideo)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [videoId]);

  async function handleAnalyze() {
    if (!videoId) return;
    setAnalyzing(true);
    setError("");
    try {
      const session = await api.triggerAnalysis(videoId);
      router.push(`/sessions/${session.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start the breakdown");
      setAnalyzing(false);
    }
  }

  async function handleDelete() {
    if (!videoId) return;
    setError("");
    try {
      await api.deleteVideo(videoId);
      router.push("/dashboard");
    } catch {
      setError("Couldn't delete the clip. Try again.");
      setConfirmingDelete(false);
    }
  }

  if (loading) return <LoadingBlock />;

  if (!video) {
    return (
      <div className="py-24 text-center">
        <h1 className="display text-5xl text-chalk">Clip not found</h1>
        <p className="mt-3 text-mute">It may have been deleted.</p>
        <ButtonLink href="/dashboard" variant="outline" className="mt-6">
          Back to camp
        </ButtonLink>
      </div>
    );
  }

  const details = [
    ["Length", formatDuration(video.duration_seconds)],
    ["Size", formatBytes(video.file_size_bytes)],
    ["Format", video.format.toUpperCase()],
    ["Added", new Date(video.created_at).toLocaleString()],
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow mb-2 flex items-center gap-3 text-blood">
            Clip <StatusBadge status={video.status} />
          </p>
          <h1 className="display truncate text-4xl text-chalk sm:text-5xl">
            {video.original_filename}
          </h1>
        </div>
        <Button size="lg" onClick={handleAnalyze} disabled={analyzing || video.status === "processing"}>
          <BoltIcon /> {analyzing ? "Starting..." : "Break it down"}
        </Button>
      </header>

      {error && <ErrorNote>{error}</ErrorNote>}

      <VideoPlayer src={stream.url} onSrcError={stream.refreshIfExpired} />

      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-4">
        {details.map(([label, value]) => (
          <div key={label} className="bg-panel p-4">
            <dt className="eyebrow">{label}</dt>
            <dd className="mt-1.5 font-medium text-chalk">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
        <p className="text-sm text-mute">
          Deleting a clip also removes its breakdowns and the overlay video.
        </p>
        {confirmingDelete ? (
          <div className="flex gap-2">
            <Button variant="danger" size="sm" onClick={handleDelete}>
              Yes, delete it
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmingDelete(false)}>
              Keep it
            </Button>
          </div>
        ) : (
          <Button variant="danger" size="sm" onClick={() => setConfirmingDelete(true)}>
            Delete clip
          </Button>
        )}
      </div>
    </div>
  );
}
