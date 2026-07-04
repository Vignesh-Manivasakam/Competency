# Frontend — Manager Portal

## Plan 18 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the complete Manager Portal as a React 18 + TypeScript SPA using Vite, shadcn/ui, and TailwindCSS. This includes the application shell with sidebar navigation, all seven manager-facing pages (Dashboard, Competencies, CompetencyDetail, CompetencyWizard, Employees, EmployeeDetail, Reviews), the react-flow Skill DAG Editor with client-side cycle detection, chart components, API client with JWT interceptors, Zustand auth store, and TanStack Query hooks for server state management.

### Prerequisites

- **Plan 7** (Competency API & Decomposition) — CRUD endpoints, decompose/validate routes, skill DAG management API
- **Plan 17** (Manager Dashboard API) — Dashboard stats, team progress, skill gap heatmap, pending reviews endpoints

### Spec References

| Section | Content |
|---------|---------|
| §10.1 | Application Structure — React 18 + Vite SPA, shadcn/ui, TailwindCSS |
| §10.2 | Manager Portal — Page and Component Breakdown (7 routes) |
| §10.2.1 | Skill DAG Editor Component — react-flow canvas, cycle detection, validation |
| §11 | Frontend Project Structure — full directory layout |

---

### Files to Create/Modify

```
frontend/src/
├── api/
│   ├── client.ts              # Axios instance with JWT interceptor
│   ├── competencies.ts        # Competency API functions
│   ├── dashboard.ts           # Dashboard API functions
│   └── employees.ts           # Employee API functions
├── store/
│   └── authStore.ts           # Zustand auth state
├── hooks/
│   ├── useCompetencyGraph.ts  # DAG state + cycle detection hook
│   └── useEmployeeState.ts    # Employee data hook
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx       # Main layout with sidebar
│   │   └── Sidebar.tsx        # Navigation sidebar
│   ├── dag/
│   │   ├── SkillDAGEditor.tsx # react-flow DAG canvas
│   │   └── SkillNode.tsx      # Custom react-flow node
│   └── charts/
│       ├── MasteryProgressChart.tsx  # Recharts line chart
│       └── SkillRadarChart.tsx       # Recharts radar chart
├── pages/manager/
│   ├── Dashboard.tsx          # StatsCards, TeamProgressTable, SkillGapHeatmap
│   ├── Competencies.tsx       # CompetencyList with status badges
│   ├── CompetencyWizard.tsx   # 4-step creation wizard
│   ├── CompetencyDetail.tsx   # Header + DAG Editor + VersionHistory
│   ├── Employees.tsx          # EmployeeTable with mastery chips
│   ├── EmployeeDetail.tsx     # Profile, matrix, timeline, chart
│   └── Reviews.tsx            # PendingReviewsList, MasteryOverrideModal
└── App.tsx                    # Router setup
```

---

### Detailed Implementation Steps

#### Step 1: Axios API Client with JWT Interceptor (§10.1)

```typescript
// frontend/src/api/client.ts
/**
 * Axios instance with JWT interceptor and token refresh.
 * From §10.1: All API calls use Authorization: Bearer <token>.
 * From §11: api/client.ts — Axios instance with interceptors.
 */
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/authStore";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// Request interceptor — attach JWT
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — handle 401 + token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = useAuthStore.getState().refreshToken;

      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE_URL}/api/v1/auth/refresh`, {
            refresh_token: refreshToken,
          });
          useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
          return apiClient(originalRequest);
        } catch {
          useAuthStore.getState().logout();
          window.location.href = "/login";
        }
      } else {
        useAuthStore.getState().logout();
        window.location.href = "/login";
      }
    }

    return Promise.reject(error);
  }
);
```

#### Step 2: Zustand Auth Store (§11)

```typescript
// frontend/src/store/authStore.ts
/**
 * Zustand auth state store.
 * From §11: store/authStore.ts — Zustand auth state.
 * Stores JWT tokens, user profile, and tenant context.
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "manager" | "employee";
  tenant_id: string;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserProfile | null;
  isAuthenticated: boolean;

  setTokens: (access: string, refresh: string) => void;
  setUser: (user: UserProfile) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      setTokens: (access, refresh) =>
        set({ accessToken: access, refreshToken: refresh, isAuthenticated: true }),

      setUser: (user) => set({ user }),

      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        }),
    }),
    {
      name: "competency-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
```

#### Step 3: API Layer — Dashboard, Competencies, Employees (§8.3, §8.6)

```typescript
// frontend/src/api/dashboard.ts
/**
 * Dashboard API functions.
 * Consumes Plan 17 Manager Dashboard endpoints.
 */
import { apiClient } from "./client";

export interface DashboardStats {
  active_learners: number;
  avg_mastery: number;
  recent_upgrades: number;
  active_competencies: number;
  pending_reviews: number;
}

export interface TeamMember {
  employee_id: string;
  name: string;
  competency_name: string;
  mastery_level: number;
  progress_pct: number;
  last_activity: string;
}

export interface SkillGapCell {
  skill_name: string;
  employee_name: string;
  current_level: number;
  target_level: number;
  gap: number;
}

export const dashboardApi = {
  getStats: () =>
    apiClient.get<DashboardStats>("/dashboard/stats").then((r) => r.data),

  getTeamProgress: (params?: { competency_id?: string; limit?: number }) =>
    apiClient
      .get<TeamMember[]>("/dashboard/team-progress", { params })
      .then((r) => r.data),

  getSkillGapHeatmap: (competency_id: string) =>
    apiClient
      .get<SkillGapCell[]>(`/dashboard/skill-gaps/${competency_id}`)
      .then((r) => r.data),

  getPendingReviews: () =>
    apiClient.get("/dashboard/pending-reviews").then((r) => r.data),
};
```

```typescript
// frontend/src/api/competencies.ts
/**
 * Competency API functions.
 * Consumes Plan 7 competency endpoints (§8.3).
 */
import { apiClient } from "./client";

export interface Competency {
  id: string;
  name: string;
  description: string;
  status: "draft" | "under_review" | "active" | "deprecated";
  business_relevance: string;
  target_roles: string[];
  decomp_confidence: number | null;
  version_major: number;
  version_minor: number;
  created_at: string;
}

export interface SkillNode {
  id: string;
  name: string;
  description: string;
  hierarchy_level: number;
  difficulty_level: number;
  learning_strategy: string;
  estimated_minutes: number;
}

export interface SkillEdge {
  prerequisite_id: string;
  dependent_id: string;
  strength: number;
}

export interface SkillDAG {
  nodes: SkillNode[];
  edges: SkillEdge[];
}

export interface DecomposeResponse {
  job_id: string;
  status: "running" | "completed" | "failed";
  result?: SkillDAG;
  error?: string;
}

export const competencyApi = {
  list: () =>
    apiClient.get<Competency[]>("/competencies").then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Competency>(`/competencies/${id}`).then((r) => r.data),

  create: (data: { name: string; description: string; business_relevance: string; target_roles: string[] }) =>
    apiClient.post<Competency>("/competencies", data).then((r) => r.data),

  update: (id: string, data: Partial<Competency>) =>
    apiClient.put<Competency>(`/competencies/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/competencies/${id}`).then((r) => r.data),

  // AI Decomposition (§21.1 Flow 1)
  triggerDecompose: (id: string, params: { industry_context?: string; max_depth?: number }) =>
    apiClient
      .post<{ job_id: string; status: string }>(`/competencies/${id}/decompose`, params)
      .then((r) => r.data),

  pollDecompose: (id: string, jobId: string) =>
    apiClient
      .get<DecomposeResponse>(`/competencies/${id}/decompose/${jobId}`)
      .then((r) => r.data),

  // Manager validation (§8.3)
  validate: (id: string, data: { approved_nodes: string[]; removed_nodes: string[] }) =>
    apiClient.post(`/competencies/${id}/validate`, data).then((r) => r.data),

  // Skill DAG management
  getSkillDAG: (id: string) =>
    apiClient.get<SkillDAG>(`/competencies/${id}/skills`).then((r) => r.data),

  addSkillNode: (id: string, data: Partial<SkillNode>) =>
    apiClient.post<SkillNode>(`/competencies/${id}/skills`, data).then((r) => r.data),

  updateSkillNode: (id: string, skillId: string, data: Partial<SkillNode>) =>
    apiClient.put<SkillNode>(`/competencies/${id}/skills/${skillId}`, data).then((r) => r.data),

  deleteSkillNode: (id: string, skillId: string) =>
    apiClient.delete(`/competencies/${id}/skills/${skillId}`).then((r) => r.data),

  addEdge: (id: string, data: { prerequisite_name: string; dependent_name: string; strength: number }) =>
    apiClient.post(`/competencies/${id}/skills/edges`, data).then((r) => r.data),

  removeEdge: (id: string, data: { prerequisite_name: string; dependent_name: string }) =>
    apiClient.delete(`/competencies/${id}/skills/edges`, { data }).then((r) => r.data),

  getVersions: (id: string) =>
    apiClient.get(`/competencies/${id}/versions`).then((r) => r.data),
};
```

```typescript
// frontend/src/api/employees.ts
/**
 * Employee API functions.
 * Consumes Plan 17 employee management endpoints.
 */
import { apiClient } from "./client";

export interface EmployeeSummary {
  id: string;
  full_name: string;
  email: string;
  role: string;
  competencies: {
    competency_id: string;
    competency_name: string;
    mastery_level: number;
    progress_pct: number;
  }[];
}

export interface EmployeeProfile extends EmployeeSummary {
  department: string;
  hire_date: string;
  assessment_history: AssessmentRecord[];
}

export interface AssessmentRecord {
  id: string;
  skill_name: string;
  score: number;
  mastery_level_before: number;
  mastery_level_after: number;
  completed_at: string;
}

export interface CompetencyMatrix {
  competency_id: string;
  competency_name: string;
  skills: {
    skill_id: string;
    skill_name: string;
    mastery_level: number;
    target_level: number;
    last_assessed: string | null;
  }[];
}

export const employeeApi = {
  list: (params?: { skill_gap?: boolean; competency_id?: string }) =>
    apiClient
      .get<EmployeeSummary[]>("/employees", { params })
      .then((r) => r.data),

  get: (id: string) =>
    apiClient.get<EmployeeProfile>(`/employees/${id}`).then((r) => r.data),

  getCompetencyMatrix: (id: string) =>
    apiClient
      .get<CompetencyMatrix[]>(`/employees/${id}/competency-matrix`)
      .then((r) => r.data),

  getAssessmentHistory: (id: string, params?: { limit?: number }) =>
    apiClient
      .get<AssessmentRecord[]>(`/employees/${id}/assessments`, { params })
      .then((r) => r.data),

  overrideMastery: (
    employeeId: string,
    data: { skill_id: string; new_level: number; reason: string }
  ) =>
    apiClient
      .post(`/employees/${employeeId}/mastery-override`, data)
      .then((r) => r.data),
};
```

#### Step 4: Layout Shell & Sidebar (§10.1)

```tsx
// frontend/src/components/layout/Sidebar.tsx
/**
 * Manager portal sidebar navigation.
 * From §10.2: Routes — /dashboard, /competencies, /employees, /reviews.
 */
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  BookOpen,
  Users,
  ClipboardCheck,
  LogOut,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/competencies", label: "Competencies", icon: BookOpen },
  { to: "/employees", label: "Employees", icon: Users },
  { to: "/reviews", label: "Reviews", icon: ClipboardCheck },
] as const;

export function Sidebar() {
  const { user, logout } = useAuthStore();

  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-card">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <BookOpen className="h-6 w-6 text-primary" />
        <span className="text-lg font-semibold">Competency AI</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User section */}
      <div className="border-t p-4">
        <div className="mb-2 text-sm">
          <p className="font-medium">{user?.full_name}</p>
          <p className="text-xs text-muted-foreground">{user?.role}</p>
        </div>
        <Button variant="ghost" size="sm" className="w-full justify-start" onClick={logout}>
          <LogOut className="mr-2 h-4 w-4" />
          Sign Out
        </Button>
      </div>
    </aside>
  );
}
```

```tsx
// frontend/src/components/layout/AppShell.tsx
/**
 * Main layout shell — sidebar + content area.
 * From §10.1: SPA with persistent navigation sidebar.
 */
import { Outlet, Navigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useAuthStore } from "@/store/authStore";

export function AppShell() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
```

#### Step 5: Custom react-flow Skill Node (§10.2.1)

```tsx
// frontend/src/components/dag/SkillNode.tsx
/**
 * Custom react-flow node for skill DAG.
 * From §10.2.1: Nodes display name, level badge, difficulty indicator.
 */
import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface SkillNodeData {
  label: string;
  description: string;
  hierarchy_level: number;
  difficulty_level: number;
  learning_strategy: string;
  estimated_minutes: number;
  mastery_level?: number;
}

const DIFFICULTY_COLORS: Record<number, string> = {
  1: "bg-green-100 text-green-800 border-green-300",
  2: "bg-yellow-100 text-yellow-800 border-yellow-300",
  3: "bg-orange-100 text-orange-800 border-orange-300",
  4: "bg-red-100 text-red-800 border-red-300",
  5: "bg-purple-100 text-purple-800 border-purple-300",
};

const LEVEL_LABELS = ["", "Foundational", "Intermediate", "Advanced", "Expert"];

function SkillNodeComponent({ data, selected }: NodeProps) {
  const nodeData = data as unknown as SkillNodeData;
  const difficultyClass = DIFFICULTY_COLORS[nodeData.difficulty_level] ?? DIFFICULTY_COLORS[1];

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-sm transition-shadow min-w-[180px]",
        selected ? "border-primary shadow-md" : "border-border"
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-primary" />

      {/* Skill name */}
      <p className="text-sm font-semibold leading-tight">{nodeData.label}</p>

      {/* Badges row */}
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <Badge variant="outline" className={cn("text-[10px]", difficultyClass)}>
          Lvl {nodeData.difficulty_level}
        </Badge>
        <Badge variant="secondary" className="text-[10px]">
          {LEVEL_LABELS[nodeData.hierarchy_level] ?? "—"}
        </Badge>
      </div>

      {/* Time estimate */}
      <p className="mt-1 text-[10px] text-muted-foreground">
        ~{nodeData.estimated_minutes} min
      </p>

      <Handle type="source" position={Position.Bottom} className="!bg-primary" />
    </div>
  );
}

export const SkillNodeType = memo(SkillNodeComponent);
```

#### Step 6: Competency Graph Hook with Cycle Detection (§10.2.1)

```typescript
// frontend/src/hooks/useCompetencyGraph.ts
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

interface CycleCheckResult {
  hasCycle: boolean;
  cycleNodes: string[];
}

/**
 * Topological sort–based cycle detection.
 * From §10.2.1: Client-side with topological sort before save.
 * Uses Kahn's algorithm — if not all nodes are visited, a cycle exists.
 */
function detectCycle(nodes: Node[], edges: Edge[]): CycleCheckResult {
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
    adjacency.get(edge.source)?.push(edge.target);
    inDegree.set(edge.target, (inDegree.get(edge.target) ?? 0) + 1);
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
```

#### Step 7: Skill DAG Editor Component (§10.2.1)

```tsx
// frontend/src/components/dag/SkillDAGEditor.tsx
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
  initialEdges: { id: string; source: string; target: string; label?: string }[];
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
      setSelectedNode(node as Node<SkillNodeData>);
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
```

#### Step 8: Chart Components (§10.2)

```tsx
// frontend/src/components/charts/MasteryProgressChart.tsx
/**
 * Line chart showing mastery progression over time.
 * From §10.2: EmployeeDetail includes MasteryProgressChart.
 */
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DataPoint {
  date: string;
  mastery_level: number;
  score: number;
}

interface MasteryProgressChartProps {
  data: DataPoint[];
  title?: string;
}

export function MasteryProgressChart({
  data,
  title = "Mastery Progress",
}: MasteryProgressChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="date" className="text-xs" />
            <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} className="text-xs" />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
              }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="mastery_level"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              name="Mastery Level"
              dot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="hsl(var(--chart-2))"
              strokeWidth={1}
              strokeDasharray="5 5"
              name="Assessment Score"
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
```

```tsx
// frontend/src/components/charts/SkillRadarChart.tsx
/**
 * Radar chart showing skill competency across multiple dimensions.
 * From §10.2: EmployeeDetail visualisation.
 */
import {
  ResponsiveContainer,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface RadarPoint {
  skill: string;
  current: number;
  target: number;
}

interface SkillRadarChartProps {
  data: RadarPoint[];
  title?: string;
}

export function SkillRadarChart({
  data,
  title = "Skill Competency Radar",
}: SkillRadarChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={350}>
          <RadarChart data={data}>
            <PolarGrid />
            <PolarAngleAxis dataKey="skill" className="text-xs" />
            <PolarRadiusAxis domain={[0, 5]} tickCount={6} />
            <Tooltip />
            <Radar
              name="Current"
              dataKey="current"
              stroke="hsl(var(--primary))"
              fill="hsl(var(--primary))"
              fillOpacity={0.3}
            />
            <Radar
              name="Target"
              dataKey="target"
              stroke="hsl(var(--chart-4))"
              fill="hsl(var(--chart-4))"
              fillOpacity={0.1}
            />
          </RadarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
```

#### Step 9: Manager Dashboard Page (§10.2)

```tsx
// frontend/src/pages/manager/Dashboard.tsx
/**
 * Manager Dashboard — StatsCards, TeamProgressTable, SkillGapHeatmap, PendingReviewsAlert.
 * From §10.2: /dashboard route components.
 */
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/api/dashboard";
import { competencyApi } from "@/api/competencies";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Users, TrendingUp, Award, AlertCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

const MASTERY_COLORS = [
  "bg-gray-200", "bg-red-200", "bg-orange-200",
  "bg-yellow-200", "bg-blue-200", "bg-green-200",
] as const;

export default function Dashboard() {
  const [heatmapCompetency, setHeatmapCompetency] = useState<string>("");

  const statsQuery = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: dashboardApi.getStats,
  });

  const teamQuery = useQuery({
    queryKey: ["dashboard", "team-progress"],
    queryFn: () => dashboardApi.getTeamProgress({ limit: 20 }),
  });

  const competenciesQuery = useQuery({
    queryKey: ["competencies"],
    queryFn: competencyApi.list,
  });

  const heatmapQuery = useQuery({
    queryKey: ["dashboard", "skill-gaps", heatmapCompetency],
    queryFn: () => dashboardApi.getSkillGapHeatmap(heatmapCompetency),
    enabled: !!heatmapCompetency,
  });

  const reviewsQuery = useQuery({
    queryKey: ["dashboard", "pending-reviews"],
    queryFn: dashboardApi.getPendingReviews,
  });

  const stats = statsQuery.data;
  const pendingCount = (reviewsQuery.data as unknown[])?.length ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Manager Dashboard</h1>

      {/* StatsCards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Active Learners</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.active_learners ?? "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Avg Mastery</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {stats?.avg_mastery != null ? stats.avg_mastery.toFixed(1) : "—"}/5
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Recent Upgrades</CardTitle>
            <Award className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.recent_upgrades ?? "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Pending Reviews</CardTitle>
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.pending_reviews ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      {/* PendingReviewsAlert */}
      {pendingCount > 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Pending Reviews</AlertTitle>
          <AlertDescription>
            You have {pendingCount} competencies awaiting validation.{" "}
            <Link to="/reviews" className="font-medium underline">
              Review now →
            </Link>
          </AlertDescription>
        </Alert>
      )}

      {/* TeamProgressTable */}
      <Card>
        <CardHeader>
          <CardTitle>Team Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Competency</TableHead>
                <TableHead>Mastery</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Last Activity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {teamQuery.data?.map((member) => (
                <TableRow key={`${member.employee_id}-${member.competency_name}`}>
                  <TableCell>
                    <Link
                      to={`/employees/${member.employee_id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {member.name}
                    </Link>
                  </TableCell>
                  <TableCell>{member.competency_name}</TableCell>
                  <TableCell>
                    <Badge className={MASTERY_COLORS[member.mastery_level]}>
                      {member.mastery_level}/5
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${member.progress_pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {member.progress_pct}%
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {new Date(member.last_activity).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* SkillGapHeatmap */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Skill Gap Heatmap</CardTitle>
          <Select value={heatmapCompetency} onValueChange={setHeatmapCompetency}>
            <SelectTrigger className="w-[250px]">
              <SelectValue placeholder="Select competency" />
            </SelectTrigger>
            <SelectContent>
              {competenciesQuery.data?.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          {heatmapQuery.data ? (
            <div className="grid gap-1" style={{
              gridTemplateColumns: `repeat(${Math.min(heatmapQuery.data.length, 10)}, 1fr)`,
            }}>
              {heatmapQuery.data.map((cell, i) => (
                <div
                  key={i}
                  className="flex flex-col items-center rounded p-2 text-[10px]"
                  style={{
                    backgroundColor: `hsl(0, ${Math.min(cell.gap * 25, 100)}%, 90%)`,
                  }}
                  title={`${cell.employee_name}: ${cell.skill_name} — gap ${cell.gap}`}
                >
                  <span className="truncate font-medium">{cell.skill_name}</span>
                  <span>{cell.gap > 0 ? `-${cell.gap}` : "✓"}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Select a competency to view skill gaps.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

#### Step 10: Competency List & Wizard Pages (§10.2)

```tsx
// frontend/src/pages/manager/Competencies.tsx
/**
 * Competency list page — CompetencyList with status badges, CompetencyCreateButton.
 * From §10.2: /competencies route.
 */
import { useQuery } from "@tanstack/react-query";
import { competencyApi } from "@/api/competencies";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Plus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  under_review: "secondary",
  draft: "outline",
  deprecated: "destructive",
};

export default function Competencies() {
  const navigate = useNavigate();
  const { data: competencies, isLoading } = useQuery({
    queryKey: ["competencies"],
    queryFn: competencyApi.list,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Competencies</h1>
        <Button onClick={() => navigate("/competencies/new")}>
          <Plus className="mr-2 h-4 w-4" /> Create Competency
        </Button>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {competencies?.map((comp) => (
            <Link key={comp.id} to={`/competencies/${comp.id}`}>
              <Card className="cursor-pointer transition-shadow hover:shadow-md">
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <h3 className="font-semibold">{comp.name}</h3>
                    <Badge variant={STATUS_VARIANT[comp.status] ?? "outline"}>
                      {comp.status}
                    </Badge>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                    {comp.description}
                  </p>
                  <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                    <span>v{comp.version_major}.{comp.version_minor}</span>
                    {comp.decomp_confidence != null && (
                      <span>AI Confidence: {(comp.decomp_confidence * 100).toFixed(0)}%</span>
                    )}
                    <span>{comp.target_roles?.join(", ")}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
```

```tsx
// frontend/src/pages/manager/CompetencyWizard.tsx
/**
 * 4-step competency creation wizard.
 * From §10.2: /competencies/new
 *   Step 1: Definition form
 *   Step 2: AI decompose trigger + spinner
 *   Step 3: DAG review (react-flow preview)
 *   Step 4: Validation / approve
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { competencyApi, type Competency } from "@/api/competencies";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, CheckCircle2, ArrowRight, ArrowLeft } from "lucide-react";

// Zod schema for Step 1 — definition form
const competencySchema = z.object({
  name: z.string().min(3, "Name must be at least 3 characters"),
  description: z.string().min(10, "Description must be at least 10 characters"),
  business_relevance: z.string().min(5, "Explain why this competency matters"),
  target_roles: z.string().min(1, "Enter at least one role"),
  industry_context: z.string().optional(),
  max_depth: z.number().min(1).max(5).default(3),
});

type FormValues = z.infer<typeof competencySchema>;

const STEPS = ["Definition", "AI Decomposition", "DAG Review", "Validation"] as const;

export default function CompetencyWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [competency, setCompetency] = useState<Competency | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [decompStatus, setDecompStatus] = useState<string>("idle");

  const form = useForm<FormValues>({
    resolver: zodResolver(competencySchema),
    defaultValues: { max_depth: 3 },
  });

  // Step 1 → Create competency
  const createMutation = useMutation({
    mutationFn: (values: FormValues) =>
      competencyApi.create({
        name: values.name,
        description: values.description,
        business_relevance: values.business_relevance,
        target_roles: values.target_roles.split(",").map((r) => r.trim()),
      }),
    onSuccess: (data) => {
      setCompetency(data);
      setStep(1);
    },
  });

  // Step 2 → Trigger AI decomposition + poll (§21.1 Flow 1)
  const decomposeMutation = useMutation({
    mutationFn: async () => {
      if (!competency) throw new Error("No competency");
      const values = form.getValues();
      const { job_id } = await competencyApi.triggerDecompose(competency.id, {
        industry_context: values.industry_context,
        max_depth: values.max_depth,
      });
      setJobId(job_id);
      setDecompStatus("running");

      // Poll every 3 seconds until done
      let result = { status: "running" as string };
      while (result.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        result = await competencyApi.pollDecompose(competency.id, job_id);
      }

      setDecompStatus(result.status);
      if (result.status === "failed") {
        throw new Error("Decomposition failed");
      }
      return result;
    },
    onSuccess: () => setStep(2),
  });

  // Step 4 → Validate
  const validateMutation = useMutation({
    mutationFn: () => {
      if (!competency) throw new Error("No competency");
      return competencyApi.validate(competency.id, {
        approved_nodes: [],  // All approved in simple flow
        removed_nodes: [],
      });
    },
    onSuccess: () => {
      if (competency) navigate(`/competencies/${competency.id}`);
    },
  });

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold">Create Competency</h1>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${
                i <= step
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {i < step ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
            </div>
            <span className="text-sm">{label}</span>
            {i < STEPS.length - 1 && <ArrowRight className="h-4 w-4 text-muted-foreground" />}
          </div>
        ))}
      </div>

      {/* Step 1: Definition Form */}
      {step === 0 && (
        <Card>
          <CardHeader><CardTitle>Competency Definition</CardTitle></CardHeader>
          <CardContent>
            <form
              onSubmit={form.handleSubmit((v) => createMutation.mutate(v))}
              className="space-y-4"
            >
              <div>
                <Label>Name</Label>
                <Input {...form.register("name")} placeholder="e.g. Cloud Architecture" />
                {form.formState.errors.name && (
                  <p className="text-sm text-destructive">{form.formState.errors.name.message}</p>
                )}
              </div>
              <div>
                <Label>Description</Label>
                <Textarea {...form.register("description")} rows={3} />
                {form.formState.errors.description && (
                  <p className="text-sm text-destructive">{form.formState.errors.description.message}</p>
                )}
              </div>
              <div>
                <Label>Business Relevance</Label>
                <Textarea {...form.register("business_relevance")} rows={2} />
              </div>
              <div>
                <Label>Target Roles (comma-separated)</Label>
                <Input {...form.register("target_roles")} placeholder="Backend Engineer, DevOps" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Industry Context</Label>
                  <Input {...form.register("industry_context")} placeholder="e.g. fintech" />
                </div>
                <div>
                  <Label>Max Depth (1-5)</Label>
                  <Input type="number" {...form.register("max_depth", { valueAsNumber: true })} />
                </div>
              </div>
              <Button type="submit" disabled={createMutation.isPending} className="w-full">
                {createMutation.isPending ? "Creating…" : "Create & Continue"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Step 2: AI Decomposition — trigger + spinner */}
      {step === 1 && (
        <Card>
          <CardHeader><CardTitle>AI Skill Decomposition</CardTitle></CardHeader>
          <CardContent className="flex flex-col items-center gap-4 py-8">
            {decompStatus === "idle" || decompStatus === "running" ? (
              <>
                {decomposeMutation.isPending ? (
                  <>
                    <Loader2 className="h-12 w-12 animate-spin text-primary" />
                    <p className="text-muted-foreground">
                      AI is decomposing "{competency?.name}" into skills…
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Job ID: {jobId ?? "starting…"}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-center text-muted-foreground">
                      Ready to trigger AI decomposition for "{competency?.name}".
                    </p>
                    <Button onClick={() => decomposeMutation.mutate()}>
                      Start Decomposition
                    </Button>
                  </>
                )}
              </>
            ) : decompStatus === "failed" ? (
              <>
                <p className="text-destructive">Decomposition failed. Please retry.</p>
                <Button variant="outline" onClick={() => decomposeMutation.mutate()}>
                  Retry
                </Button>
              </>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Step 3: DAG Review (simplified — full editor on detail page) */}
      {step === 2 && (
        <Card>
          <CardHeader><CardTitle>Review Skill DAG</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              The AI has generated a skill graph for "{competency?.name}".
              You can review and edit the full DAG on the competency detail page after validation.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                <ArrowLeft className="mr-1 h-3 w-3" /> Re-Decompose
              </Button>
              <Button onClick={() => setStep(3)}>
                Approve & Continue <ArrowRight className="ml-1 h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Validation */}
      {step === 3 && (
        <Card>
          <CardHeader><CardTitle>Validate & Activate</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Confirm to activate this competency. The skill graph will be locked and
              employees can begin their learning paths.
            </p>
            <Button
              onClick={() => validateMutation.mutate()}
              disabled={validateMutation.isPending}
              className="w-full"
            >
              {validateMutation.isPending ? "Validating…" : "Validate & Activate"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
```

#### Step 11: Competency Detail Page (§10.2)

```tsx
// frontend/src/pages/manager/CompetencyDetail.tsx
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

  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (!competency) return <p className="text-destructive">Competency not found.</p>;

  const rfNodes = dag ? toReactFlowNodes(dag.nodes) : [];
  const rfEdges = dag ? toReactFlowEdges(dag.edges) : [];

  return (
    <div className="space-y-6">
      {/* CompetencyHeader */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">{competency.name}</h1>
          <Badge>{competency.status}</Badge>
          <span className="text-sm text-muted-foreground">
            v{competency.version_major}.{competency.version_minor}
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
            <p className="text-sm text-muted-foreground">No version history yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

#### Step 12: Employee Pages (§10.2)

```tsx
// frontend/src/pages/manager/Employees.tsx
/**
 * Employee list — EmployeeTable with mastery level chips, filter by skill gap.
 * From §10.2: /employees route.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { employeeApi } from "@/api/employees";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Link } from "react-router-dom";

const LEVEL_LABELS = ["N/A", "Aware", "Dev", "Prof", "Adv", "Master"];

export default function Employees() {
  const [search, setSearch] = useState("");
  const [showGapsOnly, setShowGapsOnly] = useState(false);

  const { data: employees, isLoading } = useQuery({
    queryKey: ["employees", { skill_gap: showGapsOnly }],
    queryFn: () => employeeApi.list({ skill_gap: showGapsOnly || undefined }),
  });

  const filtered = employees?.filter((e) =>
    e.full_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Employees</h1>

      <div className="flex items-center gap-4">
        <Input
          placeholder="Search employees…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <div className="flex items-center gap-2">
          <Switch
            id="gap-filter"
            checked={showGapsOnly}
            onCheckedChange={setShowGapsOnly}
          />
          <Label htmlFor="gap-filter">Show skill gaps only</Label>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Competencies</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered?.map((emp) => (
              <TableRow key={emp.id}>
                <TableCell>
                  <Link
                    to={`/employees/${emp.id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    {emp.full_name}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">{emp.email}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {emp.competencies.map((c) => (
                      <Badge
                        key={c.competency_id}
                        variant="outline"
                        className="text-xs"
                        title={c.competency_name}
                      >
                        {c.competency_name}: {LEVEL_LABELS[c.mastery_level]}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
```

```tsx
// frontend/src/pages/manager/EmployeeDetail.tsx
/**
 * Employee detail — profile, CompetencyMatrixCard, AssessmentHistoryTimeline, MasteryProgressChart.
 * From §10.2: /employees/{id} route.
 */
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { employeeApi } from "@/api/employees";
import { MasteryProgressChart } from "@/components/charts/MasteryProgressChart";
import { SkillRadarChart } from "@/components/charts/SkillRadarChart";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

const MASTERY_LABELS = ["Not Started", "Awareness", "Developing", "Proficient", "Advanced", "Mastered"];

export default function EmployeeDetail() {
  const { id } = useParams<{ id: string }>();

  const { data: profile } = useQuery({
    queryKey: ["employee", id],
    queryFn: () => employeeApi.get(id!),
    enabled: !!id,
  });

  const { data: matrix } = useQuery({
    queryKey: ["employee", id, "matrix"],
    queryFn: () => employeeApi.getCompetencyMatrix(id!),
    enabled: !!id,
  });

  const { data: history } = useQuery({
    queryKey: ["employee", id, "assessments"],
    queryFn: () => employeeApi.getAssessmentHistory(id!, { limit: 30 }),
    enabled: !!id,
  });

  if (!profile) return <p className="text-muted-foreground">Loading…</p>;

  // Build chart data from assessment history
  const progressData = (history ?? []).map((a) => ({
    date: new Date(a.completed_at).toLocaleDateString(),
    mastery_level: a.mastery_level_after,
    score: a.score,
  }));

  // Build radar data from first competency matrix
  const radarData = matrix?.[0]?.skills.map((s) => ({
    skill: s.skill_name,
    current: s.mastery_level,
    target: s.target_level,
  })) ?? [];

  return (
    <div className="space-y-6">
      {/* EmployeeProfile */}
      <div>
        <h1 className="text-2xl font-bold">{profile.full_name}</h1>
        <p className="text-muted-foreground">{profile.email} · {profile.role}</p>
      </div>

      <Separator />

      {/* Charts row */}
      <div className="grid gap-6 lg:grid-cols-2">
        <MasteryProgressChart data={progressData} />
        <SkillRadarChart data={radarData} />
      </div>

      {/* CompetencyMatrixCards */}
      {matrix?.map((m) => (
        <Card key={m.competency_id}>
          <CardHeader>
            <CardTitle>{m.competency_name}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {m.skills.map((skill) => (
                <div
                  key={skill.skill_id}
                  className="flex items-center justify-between rounded border p-3"
                >
                  <div>
                    <p className="text-sm font-medium">{skill.skill_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Target: {MASTERY_LABELS[skill.target_level]}
                    </p>
                  </div>
                  <Badge
                    variant={skill.mastery_level >= skill.target_level ? "default" : "secondary"}
                  >
                    {MASTERY_LABELS[skill.mastery_level]}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      {/* AssessmentHistoryTimeline */}
      <Card>
        <CardHeader>
          <CardTitle>Assessment History</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {(history ?? []).map((record) => (
              <div
                key={record.id}
                className="flex items-center gap-4 border-l-2 border-primary/30 pl-4"
              >
                <div className="flex-1">
                  <p className="text-sm font-medium">{record.skill_name}</p>
                  <p className="text-xs text-muted-foreground">
                    Score: {record.score} · {MASTERY_LABELS[record.mastery_level_before]} →{" "}
                    {MASTERY_LABELS[record.mastery_level_after]}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground">
                  {new Date(record.completed_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

#### Step 13: Reviews Page with Mastery Override Modal (§10.2)

```tsx
// frontend/src/pages/manager/Reviews.tsx
/**
 * PendingReviewsList + MasteryOverrideModal.
 * From §10.2: /reviews route — competencies awaiting manager validation; mastery overrides.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { dashboardApi } from "@/api/dashboard";
import { competencyApi } from "@/api/competencies";
import { employeeApi } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { CheckCircle, XCircle } from "lucide-react";

interface PendingReview {
  competency_id: string;
  competency_name: string;
  status: string;
  created_at: string;
  skill_count: number;
}

export default function Reviews() {
  const queryClient = useQueryClient();
  const [overrideModal, setOverrideModal] = useState<{
    open: boolean;
    employeeId: string;
    skillId: string;
    skillName: string;
  }>({ open: false, employeeId: "", skillId: "", skillName: "" });
  const [overrideLevel, setOverrideLevel] = useState(0);
  const [overrideReason, setOverrideReason] = useState("");

  const { data: reviews } = useQuery({
    queryKey: ["dashboard", "pending-reviews"],
    queryFn: dashboardApi.getPendingReviews,
  });

  // Approve competency mutation
  const approveMutation = useMutation({
    mutationFn: (compId: string) =>
      competencyApi.validate(compId, { approved_nodes: [], removed_nodes: [] }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["dashboard", "pending-reviews"] }),
  });

  // Mastery override mutation
  const overrideMutation = useMutation({
    mutationFn: () =>
      employeeApi.overrideMastery(overrideModal.employeeId, {
        skill_id: overrideModal.skillId,
        new_level: overrideLevel,
        reason: overrideReason,
      }),
    onSuccess: () => {
      setOverrideModal({ open: false, employeeId: "", skillId: "", skillName: "" });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const pendingList = (reviews ?? []) as PendingReview[];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Pending Reviews</h1>

      {/* PendingReviewsList */}
      {pendingList.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No pending reviews. All competencies are up to date.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {pendingList.map((review) => (
            <Card key={review.competency_id}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <h3 className="font-semibold">{review.competency_name}</h3>
                  <p className="text-sm text-muted-foreground">
                    {review.skill_count} skills · Created{" "}
                    {new Date(review.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{review.status}</Badge>
                  <Button
                    size="sm"
                    onClick={() => approveMutation.mutate(review.competency_id)}
                    disabled={approveMutation.isPending}
                  >
                    <CheckCircle className="mr-1 h-3 w-3" /> Approve
                  </Button>
                  <Button size="sm" variant="ghost">
                    <XCircle className="mr-1 h-3 w-3" /> Reject
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* MasteryOverrideModal */}
      <Dialog
        open={overrideModal.open}
        onOpenChange={(open) =>
          setOverrideModal((prev) => ({ ...prev, open }))
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Override Mastery Level</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Override mastery for: <strong>{overrideModal.skillName}</strong>
            </p>
            <div>
              <Label>New Mastery Level (0-5)</Label>
              <Input
                type="number"
                min={0}
                max={5}
                value={overrideLevel}
                onChange={(e) => setOverrideLevel(Number(e.target.value))}
              />
            </div>
            <div>
              <Label>Reason</Label>
              <Textarea
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Explain why this override is needed…"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOverrideModal((p) => ({ ...p, open: false }))}>
              Cancel
            </Button>
            <Button
              onClick={() => overrideMutation.mutate()}
              disabled={overrideMutation.isPending || !overrideReason}
            >
              {overrideMutation.isPending ? "Saving…" : "Apply Override"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

#### Step 14: Application Router (§10.1, §10.2)

```tsx
// frontend/src/App.tsx
/**
 * Root application component with React Router.
 * From §10.1: React 18 SPA with TanStack Query provider.
 * From §10.2: Manager portal routes.
 */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { AppShell } from "@/components/layout/AppShell";

// Manager pages — lazy loaded
import Dashboard from "@/pages/manager/Dashboard";
import Competencies from "@/pages/manager/Competencies";
import CompetencyWizard from "@/pages/manager/CompetencyWizard";
import CompetencyDetail from "@/pages/manager/CompetencyDetail";
import Employees from "@/pages/manager/Employees";
import EmployeeDetail from "@/pages/manager/EmployeeDetail";
import Reviews from "@/pages/manager/Reviews";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30s before refetch
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Manager portal — protected by AppShell auth gate */}
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/competencies" element={<Competencies />} />
            <Route path="/competencies/new" element={<CompetencyWizard />} />
            <Route path="/competencies/:id" element={<CompetencyDetail />} />
            <Route path="/employees" element={<Employees />} />
            <Route path="/employees/:id" element={<EmployeeDetail />} />
            <Route path="/reviews" element={<Reviews />} />
          </Route>

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Login page — Plan 19 (Employee Portal) will add auth pages */}
          <Route path="/login" element={<div>Login Page (Plan 19)</div>} />
        </Routes>
      </BrowserRouter>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
```

#### Step 15: Employee State Hook (§11)

```typescript
// frontend/src/hooks/useEmployeeState.ts
/**
 * Hook for managing employee data with TanStack Query.
 * From §11: hooks/useEmployeeState.ts — Employee data hook.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { employeeApi, type EmployeeProfile, type CompetencyMatrix } from "@/api/employees";

export function useEmployee(employeeId: string | undefined) {
  const queryClient = useQueryClient();

  const profileQuery = useQuery<EmployeeProfile>({
    queryKey: ["employee", employeeId],
    queryFn: () => employeeApi.get(employeeId!),
    enabled: !!employeeId,
  });

  const matrixQuery = useQuery<CompetencyMatrix[]>({
    queryKey: ["employee", employeeId, "matrix"],
    queryFn: () => employeeApi.getCompetencyMatrix(employeeId!),
    enabled: !!employeeId,
  });

  const assessmentQuery = useQuery({
    queryKey: ["employee", employeeId, "assessments"],
    queryFn: () => employeeApi.getAssessmentHistory(employeeId!, { limit: 50 }),
    enabled: !!employeeId,
  });

  const overrideMutation = useMutation({
    mutationFn: (data: { skill_id: string; new_level: number; reason: string }) =>
      employeeApi.overrideMastery(employeeId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employee", employeeId] });
    },
  });

  return {
    profile: profileQuery.data,
    matrix: matrixQuery.data,
    assessments: assessmentQuery.data,
    isLoading: profileQuery.isLoading,
    overrideMastery: overrideMutation.mutate,
    isOverriding: overrideMutation.isPending,
  };
}
```

---

### Verification Criteria

1. **Dashboard loads with stats**: StatsCards render active_learners, avg_mastery, recent_upgrades, pending_reviews from `/dashboard/stats`
2. **Team progress table**: TeamProgressTable fetches and displays employee mastery levels with progress bars
3. **Skill gap heatmap**: Selecting a competency renders the heatmap grid with gap colour coding
4. **Pending reviews alert**: Alert banner with link to `/reviews` appears when pendingCount > 0
5. **Competency list**: Grid of cards with status badges (active/draft/under_review/deprecated) renders from `/competencies`
6. **Competency wizard end-to-end**: Step 1 (form + zod validation) → Step 2 (POST decompose + 3s poll loop) → Step 3 (DAG preview) → Step 4 (POST validate) → redirect to detail page
7. **DAG editor renders nodes**: react-flow canvas displays SkillNode custom nodes with level badges, difficulty indicators, and prerequisite edges
8. **DAG editor toolbar**: Add Node, Delete, Re-Decompose, Save & Validate buttons functional
9. **Cycle detection blocks invalid saves**: Adding a circular edge triggers Kahn's algorithm; cycle error alert is displayed and save button is disabled
10. **Employee table mastery chips**: EmployeeTable renders per-competency mastery level badges; skill gap filter toggle works
11. **Employee detail charts**: MasteryProgressChart (line) and SkillRadarChart (radar) render with recharts from assessment history data
12. **Mastery override modal**: Dialog accepts new level + reason and POSTs to `/employees/{id}/mastery-override`
13. **JWT interceptor**: Axios request interceptor attaches Bearer token; 401 response triggers token refresh or redirect to login
14. **Auth guard**: AppShell redirects to `/login` when `isAuthenticated === false`

### Notes & Gotchas

- **react-flow import**: Use `@xyflow/react` (v12+), not the deprecated `reactflow` package — the import paths and component names differ
- **Cycle detection runs client-side**: Kahn's algorithm runs in the browser before save; the server-side Neo4j cycle check (Plan 7) is the second safety net
- **Polling strategy**: CompetencyWizard Step 2 uses `setTimeout` polling every 3s — consider upgrading to SSE/WebSocket in production
- **Zustand persist**: Auth state is persisted to localStorage; clear on logout to prevent stale tokens
- **TanStack Query staleTime**: Set to 30s globally — dashboard data refreshes on navigation but avoids excessive API calls
- **shadcn/ui components**: `Card`, `Badge`, `Button`, `Input`, `Table`, `Dialog`, `Sheet`, `Select`, `Alert`, `Switch` must be installed via `npx shadcn-ui@latest add <component>` before use
- **react-hook-form + zod**: The wizard uses `@hookform/resolvers/zod` for Step 1 validation — ensure both packages are in `package.json`
- **Layout assumption**: The AppShell uses `<Outlet />` from react-router-dom v6 for nested route rendering
