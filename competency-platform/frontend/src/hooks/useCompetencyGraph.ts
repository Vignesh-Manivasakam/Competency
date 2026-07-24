/**
 * Hook for managing DAG state with client-side cycle detection.
 * From §10.2.1: Real-time cycle detection (topological sort) before save.
 */
import { useCallback, useState } from "react";
import {
  useNodesState,
  useEdgesState,
  addEdge,
  type Node,
  type Edge,
  type Connection,
} from "@xyflow/react";
import type { SkillNodeData } from "@/components/dag/SkillNode";

export interface CycleCheckResult {
  hasCycle: boolean;
  cycleNodes: string[];
}

/**
 * Topological sort–based cycle detection.
 * From §10.2.1: Client-side with topological sort before save.
 * Uses Kahn's algorithm — if not all nodes are visited, a cycle exists.
 */
export function detectCycle(nodes: Node[], edges: Edge[]): CycleCheckResult {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const inDegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();

  // Initialise
  for (const id of nodeIds) {
    inDegree.set(id, 0);
    adjacency.set(id, []);
  }

  // Build adjacency + in-degree
  for (const edge of edges) {
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      adjacency.get(edge.source)?.push(edge.target);
      inDegree.set(edge.target, (inDegree.get(edge.target) ?? 0) + 1);
    }
  }

  // Kahn's BFS
  const queue: string[] = [];
  for (const [id, deg] of inDegree) {
    if (deg === 0) queue.push(id);
  }

  const visited = new Set<string>();
  while (queue.length > 0) {
    const current = queue.shift()!;
    visited.add(current);
    for (const neighbor of adjacency.get(current) ?? []) {
      const newDeg = (inDegree.get(neighbor) ?? 1) - 1;
      inDegree.set(neighbor, newDeg);
      if (newDeg === 0) queue.push(neighbor);
    }
  }

  const cycleNodes = [...nodeIds].filter((id) => !visited.has(id));
  return { hasCycle: cycleNodes.length > 0, cycleNodes };
}

export function useCompetencyGraph(initialNodes: Node[] = [], initialEdges: Edge[] = []) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [cycleError, setCycleError] = useState<CycleCheckResult | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node<SkillNodeData> | null>(null);

  /** Add edge with pre-flight cycle check (§10.2.1) */
  const onConnect = useCallback(
    (connection: Connection) => {
      // Speculatively add edge and check for cycles
      const speculative = addEdge(
        { ...connection, animated: true, label: "prerequisite" },
        edges
      );
      const result = detectCycle(nodes, speculative);

      if (result.hasCycle) {
        setCycleError(result);
        return; // Block the connection
      }

      setCycleError(null);
      setEdges(speculative);
    },
    [nodes, edges, setEdges]
  );

  /** Add a new blank skill node */
  const addNode = useCallback(
    (data: Partial<SkillNodeData>) => {
      const id = `skill-${Date.now()}`;
      const newNode: Node = {
        id,
        type: "skillNode",
        position: { x: Math.random() * 400 + 100, y: Math.random() * 400 + 100 },
        data: {
          label: data.label ?? "New Skill",
          description: data.description ?? "",
          hierarchy_level: data.hierarchy_level ?? 1,
          difficulty_level: data.difficulty_level ?? 1,
          learning_strategy: data.learning_strategy ?? "conceptual",
          estimated_minutes: data.estimated_minutes ?? 30,
        },
      };
      setNodes((nds) => [...nds, newNode]);
      return id;
    },
    [setNodes]
  );

  /** Delete selected nodes and their connected edges */
  const deleteSelected = useCallback(() => {
    const selectedIds = new Set(nodes.filter((n) => n.selected).map((n) => n.id));
    if (selectedIds.size === 0) return;

    setNodes((nds) => nds.filter((n) => !selectedIds.has(n.id)));
    setEdges((eds) =>
      eds.filter((e) => !selectedIds.has(e.source) && !selectedIds.has(e.target))
    );
    setCycleError(null);
  }, [nodes, setNodes, setEdges]);

  /** Validate entire graph — returns true if DAG is valid */
  const validateGraph = useCallback((): boolean => {
    const result = detectCycle(nodes, edges);
    setCycleError(result.hasCycle ? result : null);
    return !result.hasCycle;
  }, [nodes, edges]);

  /** Build payload for PUT /competencies/{id}/validate */
  const buildSavePayload = useCallback(
    (removedNodeIds: string[]) => ({
      approved_nodes: nodes.map((n) => n.id).filter((id) => !removedNodeIds.includes(id)),
      removed_nodes: removedNodeIds,
    }),
    [nodes]
  );

  return {
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
  };
}
