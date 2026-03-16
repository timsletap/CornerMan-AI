"use client";

import Link from "next/link";
import type { VideoResponse } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function VideoCard({ video }: { video: VideoResponse }) {
  return (
    <Link href={`/videos/${video.id}`}>
      <Card className="hover:border-zinc-600 transition-colors cursor-pointer h-full">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-medium text-white truncate">
              {video.original_filename}
            </h3>
            <p className="text-xs text-zinc-500 mt-0.5">{formatDate(video.created_at)}</p>
          </div>
          <StatusBadge status={video.status} />
        </div>
        <div className="flex items-center gap-4 text-xs text-zinc-400">
          <span>{formatBytes(video.file_size_bytes)}</span>
          {video.duration_seconds && (
            <span>{video.duration_seconds.toFixed(1)}s</span>
          )}
          <span className="uppercase">{video.format}</span>
        </div>
      </Card>
    </Link>
  );
}
