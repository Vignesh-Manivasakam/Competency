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
    apiClient.get<DashboardStats>("/dashboard/overview").then((r) => {
      // Map overview structure from Plan 17
      const d = r.data as unknown as Record<string, number>;
      return {
        active_learners: d.active_learners ?? 0,
        avg_mastery: d.avg_mastery_level ?? 0,
        recent_upgrades: d.recent_upgrades_30d ?? 0,
        active_competencies: d.total_competencies ?? 0,
        pending_reviews: d.pending_reviews_count ?? 0,
      } as DashboardStats;
    }),

  getTeamProgress: (params?: { competency_id?: string; limit?: number }) =>
    apiClient
      .get<{ items: Record<string, unknown>[] }>("/dashboard/team-progress", { params })
      .then((r) => {
        const items = r.data.items ?? [];
        return items.map((item) => ({
          employee_id: (item.employee_id as string) ?? "",
          name: (item.employee_name as string) ?? "Unknown",
          competency_name: (item.competency_name as string) ?? "General",
          mastery_level: (item.mastery_level as number) ?? 0,
          progress_pct: Math.round(((item.mastery_level as number ?? 0) / 5) * 100),
          last_activity: (item.last_assessed_at as string) ?? new Date().toISOString(),
        })) as TeamMember[];
      }),

  getSkillGapHeatmap: (competency_id: string) =>
    apiClient
      .get<{ items: Record<string, unknown>[] }>("/dashboard/skill-gaps", {
        params: { competency_id },
      })
      .then((r) => {
        const items = r.data.items ?? [];
        return items.map((item) => ({
          skill_name: (item.skill_name as string) ?? "",
          employee_name: (item.employee_name as string) ?? "",
          current_level: (item.current_mastery_level as number) ?? 0,
          target_level: Math.round(((item.target_mastery as number) ?? 0.8) * 5),
          gap: (item.gap_severity as number) ?? 0,
        })) as SkillGapCell[];
      }),

  getPendingReviews: () =>
    apiClient.get<{ items: Record<string, unknown>[] }>("/dashboard/pending-reviews").then((r) => r.data.items ?? []),
};
