/**
 * Custom react-flow node for skill DAG.
 * From §10.2.1: Nodes display name, level badge, difficulty indicator.
 */
import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface SkillNodeData extends Record<string, unknown> {
  label: string;
  description: string;
  hierarchy_level: number;
  difficulty_level: number;
  learning_strategy: string;
  estimated_minutes: number;
  mastery_level?: number;
}

const DIFFICULTY_COLORS: Record<number, string> = {
  1: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  2: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  3: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  4: "bg-rose-500/10 text-rose-400 border-rose-500/30",
  5: "bg-purple-500/10 text-purple-400 border-purple-500/30",
};

const LEVEL_LABELS = ["", "Foundational", "Intermediate", "Advanced", "Expert"];

function SkillNodeComponent({ data, selected }: NodeProps) {
  const nodeData = data as unknown as SkillNodeData;
  const difficultyClass = DIFFICULTY_COLORS[nodeData.difficulty_level] ?? DIFFICULTY_COLORS[1];

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-sm transition-all duration-150 min-w-[180px]",
        selected ? "border-primary shadow-md ring-2 ring-primary/20 scale-[1.02]" : "border-border"
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-primary !w-3 !h-3" />

      {/* Skill name */}
      <p className="text-sm font-semibold leading-tight">{nodeData.label || "Skill Node"}</p>

      {/* Badges row */}
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <Badge variant="outline" className={cn("text-[10px]", difficultyClass)}>
          Lvl {nodeData.difficulty_level ?? 1}
        </Badge>
        <Badge variant="secondary" className="text-[10px]">
          {LEVEL_LABELS[nodeData.hierarchy_level] ?? "—"}
        </Badge>
      </div>

      {/* Time estimate */}
      <p className="mt-1 text-[10px] text-muted-foreground">
        ~{nodeData.estimated_minutes ?? 30} min
      </p>

      <Handle type="source" position={Position.Bottom} className="!bg-primary !w-3 !h-3" />
    </div>
  );
}

export const SkillNodeType = memo(SkillNodeComponent);
