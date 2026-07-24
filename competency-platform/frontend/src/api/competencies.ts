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
