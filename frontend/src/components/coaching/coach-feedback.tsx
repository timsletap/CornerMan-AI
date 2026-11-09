"use client";

import type { CoachingFeedback } from "@/lib/types";
import { Card } from "@/components/ui/card";

interface Props {
  rawFeedback: string | null;
}

function parseFeedback(raw: string | null): CoachingFeedback | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed._parse_error || parsed._api_error) return null;
    return parsed;
  } catch {
    return null;
  }
}

function Heading() {
  return (
    <div className="mb-4 flex items-center justify-between">
      <h2 className="display text-3xl text-chalk">Corner talk</h2>
      <span className="eyebrow text-gold">Between rounds</span>
    </div>
  );
}

export function CoachFeedbackPanel({ rawFeedback }: Props) {
  const feedback = parseFeedback(rawFeedback);

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
      {feedback._note && (
        <p className="mb-4 rounded-sm border border-gold/40 bg-gold/10 px-3 py-2 text-xs text-gold">
          {feedback._note}
        </p>
      )}

      <div className="space-y-5">
        <div className="border border-blood/50 bg-blood/10 p-4">
          <p className="eyebrow text-blood">Fix this first</p>
          <p className="mt-2 font-display text-2xl font-bold uppercase italic leading-tight text-chalk">
            {feedback.one_thing}
          </p>
        </div>

        <p className="leading-relaxed text-chalk/90">{feedback.summary}</p>

        <div className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-2">
          <div className="bg-panel-2 p-4">
            <p className="eyebrow">Number to watch</p>
            <p className="mt-1.5 text-sm font-medium text-chalk">{feedback.key_metric}</p>
          </div>
          {feedback.prescribed_drill && (
            <div className="bg-panel-2 p-4">
              <p className="eyebrow">Why this drill</p>
              <p className="mt-1.5 text-sm font-medium text-chalk">
                {feedback.prescribed_drill.reasoning}
              </p>
            </div>
          )}
        </div>

        {feedback.detailed_notes && feedback.detailed_notes.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Notes</p>
            <ol className="space-y-2">
              {feedback.detailed_notes.map((note, i) => (
                <li key={i} className="flex gap-3 text-sm leading-relaxed text-mute">
                  <span className="font-mono text-xs text-blood">{String(i + 1).padStart(2, "0")}</span>
                  {note}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </Card>
  );
}
