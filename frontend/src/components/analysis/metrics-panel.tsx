import { Card } from "@/components/ui/card";

interface Props {
  totalStrikes: number | null;
  avgVelocity: number | null;
  guardScore: number | null;
}

function MetricCard({ label, value, unit, color }: {
  label: string;
  value: string;
  unit?: string;
  color: string;
}) {
  return (
    <Card className="text-center">
      <p className="text-xs text-zinc-400 uppercase tracking-wider">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color}`}>
        {value}
        {unit && <span className="text-lg ml-1">{unit}</span>}
      </p>
    </Card>
  );
}

export function MetricsPanel({ totalStrikes, avgVelocity, guardScore }: Props) {
  const guardColor =
    guardScore !== null
      ? guardScore >= 80 ? "text-green-400" : guardScore >= 50 ? "text-yellow-400" : "text-red-400"
      : "text-zinc-400";

  return (
    <div className="grid grid-cols-3 gap-3">
      <MetricCard
        label="Total Strikes"
        value={totalStrikes?.toString() || "--"}
        color="text-white"
      />
      <MetricCard
        label="Avg Velocity"
        value={avgVelocity?.toFixed(1) || "--"}
        unit="u/s"
        color="text-blue-400"
      />
      <MetricCard
        label="Guard Score"
        value={guardScore?.toFixed(0) || "--"}
        unit="%"
        color={guardColor}
      />
    </div>
  );
}
