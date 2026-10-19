"use client";

import { useRef, type RefObject } from "react";

interface Props {
  src: string;
  onTimeUpdate?: (timeMs: number) => void;
  videoRef?: RefObject<HTMLVideoElement | null>;
}

export function VideoPlayer({ src, onTimeUpdate, videoRef: externalRef }: Props) {
  const internalRef = useRef<HTMLVideoElement>(null);
  const ref = externalRef || internalRef;

  return (
    <div className="relative rounded-lg overflow-hidden bg-black">
      <video
        ref={ref}
        src={src}
        onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime * 1000)}
        controls
        playsInline
        className="w-full aspect-video"
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
