import type { StrikeSummary } from "@/lib/fight-stats";
import { strikeMeta } from "@/lib/strike-meta";

/** Punch selection: how many of each strike, and the split between hands. */
export function StrikeBreakdown({ summary }: { summary: StrikeSummary }) {
  if (summary.total === 0) {
    return <p className="text-sm text-mute">No strikes were detected in this clip.</p>;
  }

  const top = summary.byType[0].count;
  const leftShare = (summary.byHand.left / summary.total) * 100;

  return (
    <div className="space-y-6">
      <ul className="space-y-2.5">
        {summary.byType.map(({ type, count, share }) => {
          const meta = strikeMeta(type);
          return (
            <li key={type} className="grid grid-cols-[5.5rem_1fr_auto] items-center gap-3">
              <span className="font-display text-lg font-bold uppercase italic text-chalk">
                {meta.label}
              </span>
              <span className="h-3 bg-line">
                <span
                  className="block h-full"
                  style={{ width: `${(count / top) * 100}%`, backgroundColor: meta.color }}
                />
              </span>
              <span className="w-16 text-right font-mono text-sm text-chalk">
                {count} <span className="text-dim">{Math.round(share * 100)}%</span>
              </span>
            </li>
          );
        })}
      </ul>

      <div>
        <div className="mb-1.5 flex justify-between font-mono text-xs uppercase tracking-wider">
          <span className="text-corner">Left {summary.byHand.left}</span>
          <span className="text-dim">Hand split</span>
          <span className="text-blood">Right {summary.byHand.right}</span>
        </div>
        <div className="flex h-3 gap-0.5">
          <span className="bg-corner" style={{ width: `${leftShare}%` }} />
          <span className="flex-1 bg-blood" />
        </div>
      </div>
    </div>
  );
}
