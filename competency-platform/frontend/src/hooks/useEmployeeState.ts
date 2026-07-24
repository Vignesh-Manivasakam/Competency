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
