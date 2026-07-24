/**
 * Employee profile with skill radar chart, mastery history timeline, and badges.
 * §10.3 — SkillRadarChart, MasteryHistoryTimeline, BadgesEarned
 *
 * Uses recharts (already in Plan 18 dependencies) for the radar visualization.
 */
import React, { useEffect, useState } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Loader2, Award, TrendingUp, User } from 'lucide-react';
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from 'recharts';
import { MasteryBadge } from '@/components/session/MasteryBadge';
import { getMyProfile, type ProfileData } from '@/api/sessions';

export default function MyProfile() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMyProfile()
      .then(setProfile)
      .finally(() => setLoading(false));
  }, []);

  if (loading || !profile) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Prepare radar chart data
  const radarData = (profile.competencies ?? []).map((c) => ({
    competency: c.competency_name,
    level: c.mastery_level,
    fullMark: 5,
  }));

  return (
    <div className="space-y-6 animate-scale-in">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="h-16 w-16 rounded-full bg-primary/20 flex items-center justify-center border border-primary/30 shadow-md">
          <User className="h-8 w-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{profile.name}</h1>
          <p className="text-muted-foreground">{profile.role}</p>
        </div>
      </div>

      {/* SkillRadarChart — §10.3 */}
      <Card>
        <CardHeader>
          <CardTitle>Competency Overview</CardTitle>
        </CardHeader>
        <CardContent>
          {radarData.length > 0 ? (
            <ResponsiveContainer width="100%" height={350}>
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="80%">
                <PolarGrid />
                <PolarAngleAxis
                  dataKey="competency"
                  tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 5]}
                  tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                  tickCount={6}
                />
                <Radar
                  name="Mastery"
                  dataKey="level"
                  stroke="hsl(var(--primary))"
                  fill="hsl(var(--primary))"
                  fillOpacity={0.3}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No competency data available yet.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* MasteryHistoryTimeline — §10.3 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-5 w-5 text-primary" /> Mastery History
            </CardTitle>
          </CardHeader>
          <CardContent>
            {profile.mastery_history && profile.mastery_history.length > 0 ? (
              <div className="relative space-y-4">
                {/* Vertical timeline line */}
                <div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-muted" />

                {profile.mastery_history.map((entry, idx) => (
                  <div key={idx} className="flex gap-4 relative">
                    <div className="h-8 w-8 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center z-10 shrink-0">
                      <TrendingUp className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {entry.skill_name}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                        <MasteryBadge level={entry.old_level} size="sm" showLevel={false} />
                        <span>→</span>
                        <MasteryBadge level={entry.new_level} size="sm" showLevel={false} />
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 font-mono">
                        {new Date(entry.date).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-4 text-sm">
                No mastery changes recorded yet.
              </p>
            )}
          </CardContent>
        </Card>

        {/* BadgesEarned — §10.3 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Award className="h-5 w-5 text-amber-400" /> Badges Earned
            </CardTitle>
          </CardHeader>
          <CardContent>
            {profile.badges && profile.badges.length > 0 ? (
              <div className="grid grid-cols-2 gap-3">
                {profile.badges.map((badge) => (
                  <div
                    key={badge.id}
                    className="flex flex-col items-center gap-2 p-4 border rounded-lg bg-card text-center transition-all hover:border-amber-400/50"
                  >
                    <Award className="h-8 w-8 text-amber-400" />
                    <span className="text-sm font-medium">{badge.name}</span>
                    <span className="text-xs text-muted-foreground line-clamp-2">
                      {badge.description}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {new Date(badge.earned_at).toLocaleDateString()}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-4 text-sm">
                Complete learning sessions to earn badges!
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
