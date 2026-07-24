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

  if (!profile) return <p className="text-muted-foreground">Loading employee profile…</p>;

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
    <div className="space-y-6 animate-scale-in">
      {/* EmployeeProfile */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{profile.full_name}</h1>
        <p className="text-muted-foreground">{profile.email} · {profile.role} ({profile.department || "Engineering"})</p>
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
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {m.skills.map((skill) => (
                <div
                  key={skill.skill_id}
                  className="flex items-center justify-between rounded-lg border p-3 bg-card"
                >
                  <div>
                    <p className="text-sm font-medium">{skill.skill_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Target: {MASTERY_LABELS[skill.target_level] ?? skill.target_level}
                    </p>
                  </div>
                  <Badge
                    variant={skill.mastery_level >= skill.target_level ? "default" : "secondary"}
                  >
                    {MASTERY_LABELS[skill.mastery_level] ?? skill.mastery_level}
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
                className="flex items-center gap-4 border-l-2 border-primary/50 pl-4 py-1"
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
