/**
 * Employee API functions.
 * Consumes Plan 16/17 employee management endpoints.
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
      .post("/dashboard/mastery-override", {
        employee_id: employeeId,
        skill_id: data.skill_id,
        new_mastery_level: data.new_level,
        override_reason: data.reason,
      })
      .then((r) => r.data),
};
