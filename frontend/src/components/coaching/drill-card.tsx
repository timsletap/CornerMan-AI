import type { DrillRecommendationResponse } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function DrillCard({ rec }: { rec: DrillRecommendationResponse }) {
  const { drill } = rec;
  const difficultyLabel = ["", "Easy", "Medium", "Hard", "Expert", "Elite"][drill.difficulty_level] || "?";

  return (
    <Card className="space-y-2">
      <div className="flex items-start justify-between">
        <h4 className="text-sm font-medium text-white">{drill.name}</h4>
        <Badge color={drill.difficulty_level <= 2 ? "green" : drill.difficulty_level <= 3 ? "yellow" : "red"}>
          {difficultyLabel}
        </Badge>
      </div>
      <p className="text-sm text-zinc-400">{drill.description}</p>
      <div className="flex items-center gap-2">
        <Badge color="zinc">{drill.error_type.replace("_", " ")}</Badge>
        <span className="text-xs text-zinc-500">Priority: {rec.priority}</span>
      </div>
    </Card>
  );
}
