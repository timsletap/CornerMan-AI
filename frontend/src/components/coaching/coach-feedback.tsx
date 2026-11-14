"use client";

import { parseCoachingFeedback } from "@/lib/coaching-report";
import { Card } from "@/components/ui/card";

interface Props {
  rawFeedback: string | null;
}

function Heading() {
  return (
    <div className="mb-4 flex items-center justify-between">
      <h2 className="display text-3xl text-chalk">Corner talk</h2>
      <span className="eyebrow text-gold">Between rounds</span>
    </div>
  );
}

function formatTime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function CoachFeedbackPanel({ rawFeedback }: Props) {
  const feedback = parseCoachingFeedback(rawFeedback);

  if (!rawFeedback) {
    return (
      <Card accent="gold">
        <Heading />
        <p className="text-sm text-mute">No coaching notes for this round yet.</p>
      </Card>
    );
  }

  if (!feedback) {
    return (
      <Card accent="gold">
        <Heading />
        <p className="text-sm leading-relaxed text-chalk">{rawFeedback}</p>
      </Card>
    );
  }

  return (
    <Card accent="gold">
      <Heading />
      {feedback.notice && (
        <p className="mb-4 rounded-sm border border-gold/40 bg-gold/10 px-3 py-2 text-xs text-gold">
          {feedback.notice}
        </p>
      )}

      <div className="space-y-5">
        {feedback.oneThing && (
          <div className="border border-blood/50 bg-blood/10 p-4">
            <p className="eyebrow text-blood">Fix this first</p>
            <p className="mt-2 font-display text-2xl font-bold uppercase italic leading-tight text-chalk">
              {feedback.oneThing}
            </p>
          </div>
        )}

        <p className="leading-relaxed text-chalk/90">{feedback.summary}</p>

        <div className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-2">
          <div className="bg-panel-2 p-4">
            <p className="eyebrow">Number to watch</p>
            <p className="mt-1.5 text-sm font-medium text-chalk">{feedback.keyMetric}</p>
          </div>
          {feedback.drillReasoning && (
            <div className="bg-panel-2 p-4">
              <p className="eyebrow">Why this drill</p>
              <p className="mt-1.5 text-sm font-medium text-chalk">{feedback.drillReasoning}</p>
            </div>
          )}
        </div>

        {feedback.notes.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Notes</p>
            <ol className="space-y-2">
              {feedback.notes.map((note, i) => (
                <li key={i} className="flex gap-3 text-sm leading-relaxed text-mute">
                  <span className="font-mono text-xs text-blood">{String(i + 1).padStart(2, "0")}</span>
                  <span>
                    {note.tMs !== null && (
                      <span className="mr-2 font-mono text-xs text-gold">{formatTime(note.tMs)}</span>
                    )}
                    {note.text}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </Card>
  );
}
