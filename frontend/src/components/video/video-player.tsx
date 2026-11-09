"use client";

import { useRef, type RefObject } from "react";

interface Props {
  /** Signed media URL; null while it is being fetched. */
  src: string | null;
  onTimeUpdate?: (timeMs: number) => void;
  videoRef?: RefObject<HTMLVideoElement | null>;
  /** Called when playback errors, e.g. because the signed URL expired. */
  onSrcError?: () => void;
}

export function VideoPlayer({ src, onTimeUpdate, videoRef: externalRef, onSrcError }: Props) {
  const internalRef = useRef<HTMLVideoElement>(null);
  const ref = externalRef || internalRef;
  // Playback position to restore after the src is re-signed, in seconds.
  const resumeAt = useRef<number | null>(null);

  return (
    <div className="hud-frame border border-line bg-black">
      <video
        ref={ref}
        src={src ?? undefined}
        onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime * 1000)}
        onSeeked={(e) => onTimeUpdate?.(e.currentTarget.currentTime * 1000)}
        onError={(e) => {
          if (!onSrcError) return;
          resumeAt.current = e.currentTarget.currentTime;
          onSrcError();
        }}
        onLoadedMetadata={(e) => {
          if (resumeAt.current !== null) {
            e.currentTarget.currentTime = resumeAt.current;
            resumeAt.current = null;
          }
        }}
        controls
        playsInline
        className="aspect-video w-full"
        preload="metadata"
      />
    </div>
  );
}

export function seekTo(videoRef: RefObject<HTMLVideoElement | null>, timeMs: number) {
  if (videoRef.current) {
    videoRef.current.currentTime = timeMs / 1000;
  }
}
