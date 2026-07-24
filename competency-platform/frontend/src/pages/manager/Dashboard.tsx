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

const MASTERY_COLORS: Record<number, string> = {
  0: "bg-slate-500/20 text-slate-400 border-slate-500/30",
  1: "bg-rose-500/20 text-rose-400 border-rose-500/30",
  2: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  3: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  4: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  5: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
};

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
    <div className="space-y-6 animate-scale-in">
      <h1 className="text-2xl font-bold tracking-tight">Manager Dashboard</h1>

      {/* StatsCards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="glass-panel">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Active Learners</CardTitle>
            <Users className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.active_learners ?? "—"}</p>
          </CardContent>
        </Card>
        <Card className="glass-panel">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Avg Mastery</CardTitle>
            <TrendingUp className="h-4 w-4 text-emerald-400" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {stats?.avg_mastery != null ? stats.avg_mastery.toFixed(1) : "—"}/5
            </p>
          </CardContent>
        </Card>
        <Card className="glass-panel">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Recent Upgrades</CardTitle>
            <Award className="h-4 w-4 text-amber-400" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.recent_upgrades ?? "—"}</p>
          </CardContent>
        </Card>
        <Card className="glass-panel">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Pending Reviews</CardTitle>
            <AlertCircle className="h-4 w-4 text-rose-400" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.pending_reviews ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      {/* PendingReviewsAlert */}
      {pendingCount > 0 && (
        <Alert className="border-amber-500/50 bg-amber-500/10 text-amber-200">
          <AlertCircle className="h-4 w-4 text-amber-400" />
          <AlertTitle>Pending Reviews</AlertTitle>
          <AlertDescription>
            You have {pendingCount} competencies awaiting validation.{" "}
            <Link to="/reviews" className="font-medium underline text-amber-400 hover:text-amber-300">
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
                    <Badge variant="outline" className={MASTERY_COLORS[member.mastery_level] ?? MASTERY_COLORS[0]}>
                      {member.mastery_level}/5
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary transition-all duration-300"
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
            <div className="grid gap-2" style={{
              gridTemplateColumns: `repeat(${Math.max(Math.min(heatmapQuery.data.length, 10), 1)}, minmax(0, 1fr))`,
            }}>
              {heatmapQuery.data.map((cell, i) => (
                <div
                  key={i}
                  className="flex flex-col items-center rounded-md p-3 text-[11px] border border-border/50 transition-transform hover:scale-[1.03]"
                  style={{
                    backgroundColor: `rgba(239, 68, 68, ${Math.min(cell.gap * 0.8 + 0.1, 0.9)})`,
                  }}
                  title={`${cell.employee_name}: ${cell.skill_name} — gap ${cell.gap}`}
                >
                  <span className="truncate font-semibold text-white">{cell.skill_name}</span>
                  <span className="text-white/90 font-mono">{cell.gap > 0 ? `-${cell.gap.toFixed(2)}` : "✓"}</span>
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
