/**
 * API client for employee-facing session and competency endpoints.
 * Consumes Plan 16 REST endpoints via the shared apiClient from Plan 18.
 *
 * §10.3 — All data fetching for the five employee routes.
 */
import { apiClient } from './client';

/* ---- Types ---- */

export interface CompetencyAssignment {
  id: string;
  competency_id: string;
  competency_name: string;
  description: string;
  total_skills: number;
  mastered_skills: number;
  overall_progress: number;        // 0-100
  current_mastery_level: number;   // 0-5
  assigned_at: string;
}

export interface SkillProgress {
  skill_id: string;
  skill_name: string;
  description: string;
  mastery_level: number;           // 0-5
  mastery_label: string;           // "Not Started" | "Awareness" | ... | "Mastered"
  last_session_score: number | null;
  session_count: number;
  prerequisites_met: boolean;
}

export interface SessionSummary {
  session_id: string;
  skill_name: string;
  final_score: number;
  mastery_level: number;
  mastery_label: string;
  skills_improved: string[];
  feedback_highlights: string[];
  duration_seconds: number;
  interaction_count: number;
  started_at: string;
  completed_at: string;
}

export interface ProfileData {
  employee_id: string;
  name: string;
  role: string;
  competencies: {
    competency_name: string;
    mastery_level: number;
  }[];
  mastery_history: {
    date: string;
    skill_name: string;
    old_level: number;
    new_level: number;
  }[];
  badges: {
    id: string;
    name: string;
    description: string;
    earned_at: string;
  }[];
}

export interface LearningPathNode {
  skill_id: string;
  skill_name: string;
  mastery_level: number;
  order: number;
  is_current: boolean;
  prerequisites: string[];
}

/* ---- API Functions ---- */

/** Fetch all competency assignments for the logged-in employee. §10.3 /my-learning */
export async function getMyCompetencies(): Promise<CompetencyAssignment[]> {
  const { data } = await apiClient.get<CompetencyAssignment[]>(
    '/employees/me/competencies'
  );
  return data;
}

/** Fetch skill-level progress for a specific competency. §10.3 /my-learning/{id} */
export async function getCompetencySkills(
  competencyId: string
): Promise<SkillProgress[]> {
  const { data } = await apiClient.get<SkillProgress[]>(
    `/employees/me/competencies/${competencyId}/skills`
  );
  return data;
}

/** Fetch the learning path graph for a competency. §10.3 /my-learning/{id} */
export async function getLearningPath(
  competencyId: string
): Promise<LearningPathNode[]> {
  const { data } = await apiClient.get<LearningPathNode[]>(
    `/employees/me/competencies/${competencyId}/learning-path`
  );
  return data;
}

/** Start a new learning session for a skill. Returns the session object. */
export async function startSession(
  skillId: string
): Promise<{ session_id: string }> {
  const { data } = await apiClient.post<{ session_id: string }>(
    '/sessions',
    { skill_id: skillId }
  );
  return data;
}

/** Fetch session summary after completion. §10.3 /sessions/{id}/complete */
export async function getSessionSummary(
  sessionId: string
): Promise<SessionSummary> {
  const { data } = await apiClient.get<SessionSummary>(
    `/sessions/${sessionId}/summary`
  );
  return data;
}

/** Fetch employee profile data with radar chart info. §10.3 /my-profile */
export async function getMyProfile(): Promise<ProfileData> {
  const { data } = await apiClient.get<ProfileData>(
    '/employees/me/profile'
  );
  return data;
}
