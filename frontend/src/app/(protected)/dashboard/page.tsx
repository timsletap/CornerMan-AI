"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/context/auth-context";
import { careerStats, guardGrade } from "@/lib/fight-stats";
import { formatDate, humanize } from "@/lib/format";
import type { AnalysisSessionResponse, VideoResponse } from "@/lib/types";
import { GuardSparkline } from "@/components/analysis/guard-ring";
import { VideoCard } from "@/components/video/video-card";
import { StatusBadge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/card";
import { ArrowRightIcon, UploadIcon, XIcon } from "@/components/ui/icons";
import { ErrorNote, LoadingBlock } from "@/components/ui/spinner";

const toneText = { good: "text-go", warn: "text-gold", bad: "text-blood", none: "text-mute" };

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-panel p-5">
      <p className="eyebrow">{label}</p>
      <p className="display mt-2 text-5xl text-chalk">{value}</p>
      {hint && <p className="mt-1 text-xs text-dim">{hint}</p>}
    </div>
  );
}

function SessionCard({
  session,
  title,
  onDelete,
  deleting,
}: {
  session: AnalysisSessionResponse;
  title: string;
  onDelete: () => void;
  deleting: boolean;
}) {
  const grade = guardGrade(session.guard_score);
  const running = session.status === "queued" || session.status === "processing";

  return (
    <div className="group relative">
      <Link
        href={`/sessions/${session.id}`}
        className="block h-full rounded-md border border-line bg-panel/85 p-5 transition-colors hover:border-chalk/40"
      >
        <div className="flex items-start justify-between gap-3 pr-7">
          <div className="min-w-0">
            <p className="font-mono text-xs text-dim">{formatDate(session.created_at)}</p>
            <p className="mt-1 truncate font-medium text-chalk">{title}</p>
          </div>
          <StatusBadge status={session.status} />
        </div>

        {session.status === "completed" ? (
          <div className="mt-5 flex items-end justify-between">
            <div className="flex gap-6">
              <div>
                <p className="display text-4xl text-chalk">{session.total_strikes ?? 0}</p>
                <p className="eyebrow">Strikes</p>
              </div>
              <div>
                <p className={`display text-4xl ${toneText[grade.tone]}`}>
                  {session.guard_score === null ? "--" : `${Math.round(session.guard_score)}%`}
                </p>
                <p className="eyebrow">Guard · {grade.label}</p>
              </div>
            </div>
            <ArrowRightIcon className="text-xl text-dim transition-all group-hover:translate-x-1 group-hover:text-blood" />
          </div>
        ) : (
          <p className="mt-5 text-sm text-mute">
            {running
              ? "Breaking down your film. Open to watch progress."
              : "This one didn't finish. Open to retry."}
          </p>
        )}
      </Link>
      {!running && (
        <button
          onClick={onDelete}
          disabled={deleting}
          aria-label="Delete this analysis"
          title="Delete this analysis"
          className="absolute right-3 top-3 cursor-pointer p-1 text-dim opacity-0 transition-opacity hover:text-blood focus-visible:opacity-100 group-hover:opacity-100 disabled:cursor-wait"
        >
          <XIcon />
        </button>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [videos, setVideos] = useState<VideoResponse[]>([]);
  const [sessions, setSessions] = useState<AnalysisSessionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<Set<string>>(new Set());

  useEffect(() => {
    Promise.all([api.listVideos(), api.listSessions()])
      .then(([v, s]) => {
        setVideos(v);
        setSessions(s);
      })
      .catch(() => setError("Couldn't load your camp. Refresh to try again."))
      .finally(() => setLoading(false));
  }, []);

  async function deleteSession(sessionId: string) {
    setDeleting((prev) => new Set(prev).add(sessionId));
    try {
      await api.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch {
      setError("Couldn't delete that analysis. Try again.");
    } finally {
      setDeleting((prev) => {
        const next = new Set(prev);
        next.delete(sessionId);
        return next;
      });
    }
  }

  if (loading) return <LoadingBlock />;

  const stats = careerStats(sessions);
  const titles = new Map(videos.map((v) => [v.id, v.original_filename]));
  const firstName = user?.full_name.split(" ")[0] ?? "Fighter";
  const tape = [user?.stance, user?.weight_class, user?.experience_level].filter(
    (v): v is NonNullable<typeof v> => Boolean(v),
  );
  const isNew = videos.length === 0 && sessions.length === 0;

  return (
    <div className="space-y-12">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="eyebrow mb-2 text-blood">Fight camp</p>
          <h1 className="display text-6xl text-chalk sm:text-7xl">{firstName}&apos;s corner</h1>
          {tape.length > 0 && (
            <p className="mt-3 font-mono text-xs uppercase tracking-widest text-mute">
              {tape.map(humanize).join(" · ")}
            </p>
          )}
        </div>
        <ButtonLink href="/upload" size="lg">
          <UploadIcon /> Upload film
        </ButtonLink>
      </header>

      {error && <ErrorNote>{error}</ErrorNote>}

      {isNew ? (
        <section className="hud-frame border border-line bg-panel/70 px-6 py-16 text-center">
          <h2 className="display text-5xl text-chalk">No film yet</h2>
          <p className="mx-auto mt-3 max-w-md text-mute">
            Upload a round of bag work, pads, or sparring and you&apos;ll get a punch-by-punch
            breakdown here.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <ButtonLink href="/upload">
              <UploadIcon /> Upload your first round
            </ButtonLink>
            <ButtonLink href="/search" variant="outline">
              Import from YouTube
            </ButtonLink>
          </div>
        </section>
      ) : (
        <>
          {/* Career numbers */}
          <section
            aria-label="Your numbers"
            className="grid gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-2 lg:grid-cols-4"
          >
            <StatTile label="Rounds broken down" value={stats.sessions.toString()} />
            <StatTile label="Strikes logged" value={stats.totalStrikes.toLocaleString()} />
            <StatTile
              label="Average guard"
              value={stats.avgGuard === null ? "--" : `${Math.round(stats.avgGuard)}%`}
              hint={
                stats.bestGuard === null ? undefined : `Best round: ${Math.round(stats.bestGuard)}%`
              }
            />
            <div className="bg-panel p-5">
              <p className="eyebrow">Guard trend</p>
              {stats.guardTrend.length >= 2 ? (
                <>
                  <GuardSparkline values={stats.guardTrend} className="mt-3 h-12 w-full" />
                  <p className="mt-1 text-xs text-dim">Oldest to newest. Dashed line is 80%.</p>
                </>
              ) : (
                <p className="mt-3 text-sm text-mute">
                  Break down two rounds to see whether your guard is tightening up.
                </p>
              )}
            </div>
          </section>

          {/* Analyses */}
          {sessions.length > 0 && (
            <section className="space-y-5">
              <SectionHeading eyebrow="Film room" title="Recent breakdowns" />
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {sessions.slice(0, 6).map((s) => (
                  <SessionCard
                    key={s.id}
                    session={s}
                    title={titles.get(s.video_id) ?? "Clip"}
                    deleting={deleting.has(s.id)}
                    onDelete={() => deleteSession(s.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Clips */}
          <section className="space-y-5">
            <SectionHeading
              eyebrow="Library"
              title="Your clips"
              action={
                <ButtonLink href="/upload" variant="outline" size="sm">
                  Add a clip
                </ButtonLink>
              }
            />
            {videos.length === 0 ? (
              <p className="text-mute">No clips in your library.</p>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {videos.map((v) => (
                  <VideoCard key={v.id} video={v} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
