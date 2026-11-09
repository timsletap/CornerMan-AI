"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { canUpload, checkClip, type CheckStatus, type ClipCheck } from "@/lib/upload-rules";
import { Button, ButtonLink } from "@/components/ui/button";
import { AlertIcon, CheckIcon, FilmIcon, UploadIcon, XIcon } from "@/components/ui/icons";
import { ProgressBar } from "@/components/ui/progress-bar";
import { ErrorNote } from "@/components/ui/spinner";

interface Props {
  /** Called when the clip is uploaded; `sessionId` is set when analysis was started too. */
  onDone: (videoId: string, sessionId: string | null) => void;
}

interface Picked {
  file: File;
  previewUrl: string;
}

/** What the browser could read from the clip. `null` values mean it could not decode it. */
interface Probe {
  state: "reading" | "done";
  durationSeconds: number | null;
  width: number | null;
  height: number | null;
}

const READING: Probe = { state: "reading", durationSeconds: null, width: null, height: null };

type Stage =
  | { name: "idle" }
  | { name: "uploading"; pct: number }
  | { name: "starting" }
  | { name: "uploaded"; videoId: string; problem: string };

const statusStyle: Record<CheckStatus, string> = {
  pass: "text-go",
  warn: "text-gold",
  fail: "text-blood",
};

function CheckRow({ check }: { check: ClipCheck }) {
  const StatusIcon = check.status === "pass" ? CheckIcon : check.status === "warn" ? AlertIcon : XIcon;
  return (
    <li className="flex items-start gap-3 border-b border-line py-2.5 last:border-b-0">
      <StatusIcon className={`mt-0.5 shrink-0 text-base ${statusStyle[check.status]}`} />
      <span className="eyebrow w-24 shrink-0 pt-0.5">{check.label}</span>
      <span className={`text-sm ${check.status === "pass" ? "text-chalk" : statusStyle[check.status]}`}>
        {check.detail}
      </span>
    </li>
  );
}

export function VideoUploadZone({ onDone }: Props) {
  const [dragging, setDragging] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [probe, setProbe] = useState<Probe>(READING);
  const [analyzeAfter, setAnalyzeAfter] = useState(true);
  const [stage, setStage] = useState<Stage>({ name: "idle" });
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Free the preview's object URL when the clip is replaced or the page is left
  const previewUrl = picked?.previewUrl;
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => () => abortRef.current?.abort(), []);

  function pick(file: File | undefined) {
    if (!file) return;
    setError("");
    setStage({ name: "idle" });
    setProbe(READING);
    setPicked({ file, previewUrl: URL.createObjectURL(file) });
  }

  function clear() {
    setPicked(null);
    setError("");
    setStage({ name: "idle" });
    if (fileRef.current) fileRef.current.value = "";
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files[0]);
  }

  async function startAnalysis(videoId: string) {
    setStage({ name: "starting" });
    try {
      const session = await api.triggerAnalysis(videoId);
      onDone(videoId, session.id);
    } catch (e) {
      const problem = e instanceof Error ? e.message : "The analysis could not be started";
      setStage({ name: "uploaded", videoId, problem });
    }
  }

  async function upload() {
    if (!picked) return;
    setError("");
    setStage({ name: "uploading", pct: 0 });
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const video = await api.uploadVideo(
        picked.file,
        (pct) => setStage({ name: "uploading", pct }),
        controller.signal,
      );
      if (analyzeAfter) await startAnalysis(video.id);
      else onDone(video.id, null);
    } catch (e) {
      setStage({ name: "idle" });
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  }

  const input = (
    <input
      ref={fileRef}
      type="file"
      accept=".mp4,.mov,video/mp4,video/quicktime"
      className="hidden"
      onChange={(e) => pick(e.target.files?.[0])}
    />
  );

  if (!picked) {
    return (
      <div className="space-y-4">
        <div
          role="button"
          tabIndex={0}
          aria-label="Choose a clip to upload"
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileRef.current?.click();
            }
          }}
          className={`hud-frame flex cursor-pointer flex-col items-center justify-center border border-dashed px-6 py-16 text-center transition-colors
            focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-chalk
            ${dragging ? "border-blood bg-blood/10" : "border-line-2 bg-panel/60 hover:border-chalk/50 hover:bg-panel"}`}
        >
          <span className="octagon flex h-16 w-16 items-center justify-center bg-blood text-3xl text-white">
            <UploadIcon />
          </span>
          <p className="display mt-6 text-4xl text-chalk sm:text-5xl">
            {dragging ? "Let it go" : "Drop your round here"}
          </p>
          <p className="mt-3 text-mute">or click to pick a clip from your phone or computer</p>
          <p className="mt-6 font-mono text-xs uppercase tracking-widest text-dim">
            MP4 or MOV · up to 500 MB · up to 30 minutes
          </p>
          {input}
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
      </div>
    );
  }

  const checks = checkClip({
    name: picked.file.name,
    type: picked.file.type,
    sizeBytes: picked.file.size,
    durationSeconds: probe.durationSeconds,
    width: probe.width,
    height: probe.height,
  });
  const reading = probe.state === "reading";
  const blocked = !canUpload(checks);
  const busy = stage.name === "uploading" || stage.name === "starting";

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.2fr_1fr]">
        <div className="hud-frame border border-line bg-black">
          <video
            key={picked.previewUrl}
            src={picked.previewUrl}
            controls
            muted
            playsInline
            preload="metadata"
            className="aspect-video w-full"
            onLoadedMetadata={(e) => {
              const v = e.currentTarget;
              setProbe({
                state: "done",
                durationSeconds: Number.isFinite(v.duration) ? v.duration : null,
                width: v.videoWidth || null,
                height: v.videoHeight || null,
              });
            }}
            onError={() => setProbe({ ...READING, state: "done" })}
          />
        </div>

        <div className="rounded-md border border-line bg-panel/85 p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="eyebrow text-blood">Pre-fight check</p>
              <p className="mt-1 flex items-center gap-2 truncate font-medium text-chalk">
                <FilmIcon className="shrink-0 text-mute" />
                <span className="truncate">{picked.file.name}</span>
              </p>
              <p className="mt-0.5 text-xs text-dim">{formatBytes(picked.file.size)}</p>
            </div>
            {!busy && (
              <button
                onClick={clear}
                className="cursor-pointer text-sm text-mute underline underline-offset-4 hover:text-chalk"
              >
                Change
              </button>
            )}
          </div>
          <ul className="mt-3">
            {reading ? (
              <li className="py-2.5 text-sm text-mute">Reading the clip...</li>
            ) : (
              checks.map((check) => <CheckRow key={check.id} check={check} />)
            )}
          </ul>
        </div>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}

      {stage.name === "uploaded" ? (
        <div className="rounded-md border border-gold/40 bg-gold/10 p-5">
          <p className="font-medium text-chalk">Your clip is uploaded, but the breakdown didn&apos;t start.</p>
          <p className="mt-1 text-sm text-gold">{stage.problem}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button onClick={() => startAnalysis(stage.videoId)}>Try again</Button>
            <ButtonLink href={`/videos/${stage.videoId}`} variant="outline">
              Open the clip
            </ButtonLink>
          </div>
        </div>
      ) : busy ? (
        <div className="rounded-md border border-line bg-panel/85 p-5">
          <div className="mb-3 flex items-end justify-between">
            <p className="display text-3xl text-chalk">
              {stage.name === "uploading" ? "Uploading" : "Starting the breakdown"}
            </p>
            {stage.name === "uploading" && (
              <p className="display text-4xl text-blood">{stage.pct}%</p>
            )}
          </div>
          <ProgressBar value={stage.name === "uploading" ? stage.pct : 100} />
          {stage.name === "uploading" && (
            <button
              onClick={() => abortRef.current?.abort()}
              className="mt-3 cursor-pointer text-sm text-mute underline underline-offset-4 hover:text-chalk"
            >
              Cancel upload
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-4">
          <label className="flex cursor-pointer items-center gap-3 text-sm text-mute">
            <input
              type="checkbox"
              checked={analyzeAfter}
              onChange={(e) => setAnalyzeAfter(e.target.checked)}
              className="h-4 w-4 accent-blood"
            />
            Start the breakdown as soon as it uploads
          </label>
          <Button size="lg" onClick={upload} disabled={reading || blocked}>
            <UploadIcon /> {analyzeAfter ? "Upload and analyze" : "Upload clip"}
          </Button>
        </div>
      )}
      {input}
    </div>
  );
}
