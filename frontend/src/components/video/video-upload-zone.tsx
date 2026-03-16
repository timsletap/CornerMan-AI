"use client";

import { useState, useRef, useCallback, type DragEvent } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ProgressBar } from "@/components/ui/progress-bar";

const ALLOWED = new Set(["video/mp4", "video/quicktime"]);
const MAX_SIZE = 500 * 1024 * 1024; // 500MB

interface Props {
  onUploaded: (videoId: string) => void;
}

export function VideoUploadZone({ onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const validate = (file: File): string | null => {
    if (!ALLOWED.has(file.type) && !file.name.match(/\.(mp4|mov)$/i)) {
      return "Only .mp4 and .mov files are supported";
    }
    if (file.size > MAX_SIZE) return "File exceeds 500MB limit";
    return null;
  };

  const upload = useCallback(async (file: File) => {
    const err = validate(file);
    if (err) { setError(err); return; }
    setError("");
    setUploading(true);
    setProgress(0);
    try {
      const res = await api.uploadVideo(file, setProgress);
      onUploaded(res.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [onUploaded]);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors
          ${dragging ? "border-red-500 bg-red-950/20" : "border-zinc-700 hover:border-zinc-500 bg-zinc-900/50"}`}
      >
        <div className="text-4xl mb-3">&#127909;</div>
        <p className="text-lg font-medium text-white">
          {uploading ? "Uploading..." : "Drop your fight clip here"}
        </p>
        <p className="text-sm text-zinc-400 mt-1">
          .mp4 or .mov, max 500MB, max 60 seconds
        </p>
        {!uploading && (
          <Button variant="outline" size="sm" className="mt-4">
            Browse Files
          </Button>
        )}
        <input
          ref={fileRef}
          type="file"
          accept=".mp4,.mov,video/mp4,video/quicktime"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload(file);
          }}
        />
      </div>

      {uploading && <ProgressBar value={progress} />}

      {error && (
        <div className="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-400">
          {error}
        </div>
      )}
    </div>
  );
}
