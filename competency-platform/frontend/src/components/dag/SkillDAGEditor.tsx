/**
 * Skill DAG Editor — react-flow canvas with toolbar.
 * From §10.2.1:
 *  - Nodes: SkillNode custom node with name, level badge, difficulty
 *  - Edges: directed arrows with prerequisite labels
 *  - Toolbar: Add node, add edge, delete selected, re-run decomposition
 *  - Validation: cycle detection before save
 *  - Save: PUT /competencies/{id}/validate
 */
import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Trash2, RefreshCw, Save, AlertTriangle } from "lucide-react";
import { SkillNodeType, type SkillNodeData } from "./SkillNode";
import { useCompetencyGraph } from "@/hooks/useCompetencyGraph";
import { useMutation } from "@tanstack/react-query";
import { competencyApi } from "@/api/competencies";

interface SkillDAGEditorProps {
  competencyId: string;
  initialNodes: Node[];
  initialEdges: Edge[];
  onRerunDecompose: () => void;
}

export function SkillDAGEditor({
  competencyId,
  initialNodes,
  initialEdges,
  onRerunDecompose,
}: SkillDAGEditorProps) {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    deleteSelected,
    validateGraph,
    buildSavePayload,
    cycleError,
    selectedNode,
    setSelectedNode,
  } = useCompetencyGraph(initialNodes, initialEdges);

  const nodeTypes = useMemo(() => ({ skillNode: SkillNodeType }), []);

  // Save mutation — PUT /competencies/{id}/validate (§10.2.1)
  const saveMutation = useMutation({
    mutationFn: (payload: { approved_nodes: string[]; removed_nodes: string[] }) =>
      competencyApi.validate(competencyId, payload),
  });

  const handleSave = useCallback(() => {
    if (!validateGraph()) return;
    const payload = buildSavePayload([]);
    saveMutation.mutate(payload);
  }, [validateGraph, buildSavePayload, saveMutation]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNode(node as unknown as Node<SkillNodeData>);
    },
    [setSelectedNode]
  );

  return (
    <div className="relative h-[600px] w-full rounded-lg border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        fitView
        defaultEdgeOptions={{
          animated: false,
          type: "smoothstep",
          label: "prerequisite",
        }}
      >
        <Background gap={16} size={1} />
        <Controls />
        <MiniMap
          nodeColor={(n) => (n.selected ? "hsl(var(--primary))" : "hsl(var(--muted))")}
          className="!bg-card"
        />

        {/* Toolbar — §10.2.1 */}
        <Panel position="top-left" className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => addNode({})}>
            <Plus className="mr-1 h-3 w-3" /> Add Node
          </Button>
          <Button size="sm" variant="outline" onClick={deleteSelected}>
            <Trash2 className="mr-1 h-3 w-3" /> Delete
          </Button>
          <Button size="sm" variant="outline" onClick={onRerunDecompose}>
            <RefreshCw className="mr-1 h-3 w-3" /> Re-Decompose
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending || !!cycleError}
          >
            <Save className="mr-1 h-3 w-3" />
            {saveMutation.isPending ? "Saving…" : "Save & Validate"}
          </Button>
        </Panel>

        {/* Cycle error alert — §10.2.1 */}
        {cycleError && (
          <Panel position="top-right">
            <Alert variant="destructive" className="max-w-sm">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                Cycle detected in nodes: {cycleError.cycleNodes.join(", ")}.
                Remove the circular dependency before saving.
              </AlertDescription>
            </Alert>
          </Panel>
        )}
      </ReactFlow>

      {/* SkillNodePanel — edit on click (§10.2) */}
      <Sheet open={!!selectedNode} onOpenChange={() => setSelectedNode(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Edit Skill Node</SheetTitle>
          </SheetHeader>
          {selectedNode && (
            <div className="mt-4 space-y-4">
              <div>
                <Label>Skill Name</Label>
                <Input defaultValue={(selectedNode.data as SkillNodeData).label} />
              </div>
              <div>
                <Label>Description</Label>
                <Textarea
                  defaultValue={(selectedNode.data as SkillNodeData).description}
                  rows={3}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Difficulty (1-5)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={5}
                    defaultValue={(selectedNode.data as SkillNodeData).difficulty_level}
                  />
                </div>
                <div>
                  <Label>Est. Minutes</Label>
                  <Input
                    type="number"
                    min={5}
                    defaultValue={(selectedNode.data as SkillNodeData).estimated_minutes}
                  />
                </div>
              </div>
              <Button className="w-full">Update Node</Button>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
