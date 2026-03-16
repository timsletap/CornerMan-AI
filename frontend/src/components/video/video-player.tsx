"use client";

import { useRef, useEffect, useCallback, type RefObject } from "react";

interface Props {
  src: string;
  onTimeUpdate?: (timeMs: number) => void;
  videoRef?: RefObject<HTMLVideoElement | null>;
}

export function VideoPlayer({ src, onTimeUpdate, videoRef: externalRef }: Props) {
  const internalRef = useRef<HTMLVideoElement>(null);
  const ref = externalRef || internalRef;

  const handleTimeUpdate = useCallback(() => {
    if (ref.current && onTimeUpdate) {
      onTimeUpdate(ref.current.currentTime * 1000);
    }
  }, [ref, onTimeUpdate]);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    video.addEventListener("timeupdate", handleTimeUpdate);
    return () => video.removeEventListener("timeupdate", handleTimeUpdate);
  }, [ref, handleTimeUpdate]);

  return (
    <div className="relative rounded-lg overflow-hidden bg-black">
      <video
        ref={ref}
        src={src}
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
