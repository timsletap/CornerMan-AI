import type { DrillRecommendationResponse } from "@/lib/types";
import { errorMeta } from "@/lib/strike-meta";
import { Badge } from "@/components/ui/badge";

const DIFFICULTY = ["", "Easy", "Medium", "Hard", "Expert", "Elite"];

export function DrillCard({ rec, index }: { rec: DrillRecommendationResponse; index: number }) {
  const { drill } = rec;
  const level = drill.difficulty_level;

  return (
    <div className="flex gap-4 rounded-md border border-line bg-panel/85 p-5">
      <span className="display text-4xl text-transparent [-webkit-text-stroke:1px_var(--color-gold)]">
        {String(index + 1).padStart(2, "0")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h4 className="display text-2xl text-chalk">{drill.name}</h4>
          <Badge color={level <= 2 ? "green" : level <= 3 ? "yellow" : "red"}>
            {DIFFICULTY[level] || "?"}
          </Badge>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-mute">{drill.description}</p>
        <p className="eyebrow mt-3">Fixes · {errorMeta(drill.error_type).label}</p>
      </div>
    </div>
  );
}
