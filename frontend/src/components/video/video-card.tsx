"use client";

import Link from "next/link";
import type { VideoResponse } from "@/lib/types";
import { formatBytes, formatDate, formatDuration } from "@/lib/format";
import { StatusBadge } from "@/components/ui/badge";
import { FilmIcon } from "@/components/ui/icons";

export function VideoCard({ video }: { video: VideoResponse }) {
  return (
    <Link
      href={`/videos/${video.id}`}
      className="group flex items-center gap-4 rounded-md border border-line bg-panel/85 p-4 transition-colors hover:border-chalk/40"
    >
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-sm bg-panel-2 text-2xl text-mute transition-colors group-hover:text-blood">
        <FilmIcon />
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="truncate font-medium text-chalk">{video.original_filename}</h3>
        <p className="mt-0.5 font-mono text-xs text-dim">
          {formatDate(video.created_at)} · {formatDuration(video.duration_seconds)} ·{" "}
          {formatBytes(video.file_size_bytes)}
        </p>
      </div>
      <StatusBadge status={video.status} />
    </Link>
  );
}
