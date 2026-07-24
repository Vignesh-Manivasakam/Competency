/**
 * CompetencyDetail — header, SkillDAGEditor, VersionHistory.
 * From §10.2: /competencies/{id} route.
 */
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { competencyApi, type SkillNode as ApiSkillNode, type SkillEdge } from "@/api/competencies";
import { SkillDAGEditor } from "@/components/dag/SkillDAGEditor";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { Node, Edge } from "@xyflow/react";

/** Convert API skill nodes/edges to react-flow format */
function toReactFlowNodes(skills: ApiSkillNode[]): Node[] {
  return skills.map((s, i) => ({
    id: s.id,
    type: "skillNode",
    position: { x: (i % 4) * 250 + 50, y: Math.floor(i / 4) * 180 + 50 },
    data: {
      label: s.name,
      description: s.description,
      hierarchy_level: s.hierarchy_level,
      difficulty_level: s.difficulty_level,
      learning_strategy: s.learning_strategy,
      estimated_minutes: s.estimated_minutes,
    },
  }));
}

function toReactFlowEdges(edges: SkillEdge[]): Edge[] {
  return edges.map((e) => ({
    id: `${e.prerequisite_id}-${e.dependent_id}`,
    source: e.prerequisite_id,
    target: e.dependent_id,
    type: "smoothstep",
    label: "prerequisite",
    animated: false,
  }));
}

export default function CompetencyDetail() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const { data: competency, isLoading } = useQuery({
    queryKey: ["competency", id],
    queryFn: () => competencyApi.get(id!),
    enabled: !!id,
  });

  const { data: dag } = useQuery({
    queryKey: ["competency", id, "skills"],
    queryFn: () => competencyApi.getSkillDAG(id!),
    enabled: !!id,
  });

  const { data: versions } = useQuery({
    queryKey: ["competency", id, "versions"],
    queryFn: () => competencyApi.getVersions(id!),
    enabled: !!id,
  });

  const redecomposeMutation = useMutation({
    mutationFn: () => competencyApi.triggerDecompose(id!, { max_depth: 3 }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["competency", id] }),
  });

  if (isLoading) return <p className="text-muted-foreground">Loading competency…</p>;
  if (!competency) return <p className="text-destructive font-medium">Competency not found.</p>;

  const rfNodes = dag ? toReactFlowNodes(dag.nodes) : [];
  const rfEdges = dag ? toReactFlowEdges(dag.edges) : [];

  return (
    <div className="space-y-6 animate-scale-in">
      {/* CompetencyHeader */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{competency.name}</h1>
          <Badge>{competency.status}</Badge>
          <span className="text-sm text-muted-foreground font-mono">
            v{competency.version_major ?? 1}.{competency.version_minor ?? 0}
          </span>
        </div>
        <p className="mt-2 text-muted-foreground">{competency.description}</p>
      </div>

      <Separator />

      {/* SkillDAGEditor — §10.2.1 */}
      <Card>
        <CardHeader>
          <CardTitle>Skill DAG Editor</CardTitle>
        </CardHeader>
        <CardContent>
          <SkillDAGEditor
            competencyId={id!}
            initialNodes={rfNodes}
            initialEdges={rfEdges}
            onRerunDecompose={() => redecomposeMutation.mutate()}
          />
        </CardContent>
      </Card>

      {/* VersionHistory */}
      <Card>
        <CardHeader>
          <CardTitle>Version History</CardTitle>
        </CardHeader>
        <CardContent>
          {Array.isArray(versions) && versions.length > 0 ? (
            <ul className="space-y-2">
              {(versions as { version: string; changed_at: string; changed_by: string }[]).map(
                (v, i) => (
                  <li key={i} className="flex items-center gap-4 text-sm">
                    <Badge variant="outline">{v.version}</Badge>
                    <span className="text-muted-foreground">
                      {new Date(v.changed_at).toLocaleString()}
                    </span>
                    <span>{v.changed_by}</span>
                  </li>
                )
              )}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No version history recorded yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
