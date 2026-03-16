"use client";

import type { CoachingFeedback } from "@/lib/types";
import { Card, CardTitle } from "@/components/ui/card";

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

export function CoachFeedbackPanel({ rawFeedback }: Props) {
  const feedback = parseFeedback(rawFeedback);

  if (!rawFeedback) {
    return (
      <Card>
        <CardTitle>Coach&apos;s Corner</CardTitle>
        <p className="text-sm text-zinc-500">No coaching feedback available yet.</p>
      </Card>
    );
  }

  if (!feedback) {
    return (
      <Card>
        <CardTitle>Coach&apos;s Corner</CardTitle>
        <p className="text-sm text-zinc-300">{rawFeedback}</p>
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle>Coach&apos;s Corner</CardTitle>

      <div className="space-y-4 mt-3">
        <div>
          <p className="text-sm text-zinc-300 leading-relaxed">{feedback.summary}</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="rounded-lg bg-zinc-800/50 p-3">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Key Metric</p>
            <p className="text-sm text-white font-medium mt-1">{feedback.key_metric}</p>
          </div>
          <div className="rounded-lg bg-red-900/20 border border-red-900/30 p-3">
            <p className="text-xs text-red-400 uppercase tracking-wider">Fix This First</p>
            <p className="text-sm text-white font-medium mt-1">{feedback.one_thing}</p>
          </div>
        </div>

        {feedback.prescribed_drill && (
          <div className="rounded-lg bg-zinc-800/50 p-3">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Prescribed Drill</p>
            <p className="text-sm text-white font-medium mt-1">
              {feedback.prescribed_drill.reasoning}
            </p>
          </div>
        )}

        {feedback.detailed_notes && feedback.detailed_notes.length > 0 && (
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Detailed Notes</p>
            <ul className="space-y-1">
              {feedback.detailed_notes.map((note, i) => (
                <li key={i} className="text-sm text-zinc-400 flex gap-2">
                  <span className="text-zinc-600 flex-shrink-0">-</span>
                  {note}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
