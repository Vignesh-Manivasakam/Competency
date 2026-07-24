/**
 * Employee landing page: shows all assigned competencies with progress.
 * §10.3 — MyCompetencyCards, OverallProgressBar, ContinueLearningButton
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { BookOpen, ArrowRight, Loader2 } from 'lucide-react';
import { MasteryBadge } from '@/components/session/MasteryBadge';
import { getMyCompetencies, type CompetencyAssignment } from '@/api/sessions';

export default function MyLearning() {
  const navigate = useNavigate();
  const [competencies, setCompetencies] = useState<CompetencyAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMyCompetencies()
      .then(setCompetencies)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // Overall progress across all competencies
  const overallProgress =
    competencies.length > 0
      ? Math.round(
          competencies.reduce((sum, c) => sum + c.overall_progress, 0) /
            competencies.length
        )
      : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive text-sm font-medium">{error}</p>
        <Button variant="outline" className="mt-4" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-scale-in">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">My Learning</h1>
        <p className="text-muted-foreground">
          Track your competency progress and continue learning.
        </p>
      </div>

      {/* OverallProgressBar — §10.3 */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Overall Progress</span>
            <span className="text-sm font-semibold font-mono">{overallProgress}%</span>
          </div>
          <Progress value={overallProgress} className="h-3" />
          <p className="text-xs text-muted-foreground mt-2">
            {competencies.filter((c) => c.overall_progress === 100).length} of{' '}
            {competencies.length} competencies mastered
          </p>
        </CardContent>
      </Card>

      {/* MyCompetencyCards — §10.3 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {competencies.map((comp) => (
          <Card
            key={comp.id}
            className="hover:shadow-lg hover:border-primary/50 transition-all cursor-pointer flex flex-col justify-between"
            onClick={() => navigate(`/my-learning/${comp.competency_id}`)}
          >
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <BookOpen className="h-5 w-5 text-primary mt-1" />
                <MasteryBadge level={comp.current_mastery_level} size="sm" />
              </div>
              <CardTitle className="text-lg mt-2">{comp.competency_name}</CardTitle>
              <CardDescription className="line-clamp-2">
                {comp.description}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>
                    {comp.mastered_skills}/{comp.total_skills} skills
                  </span>
                  <span className="font-mono">{comp.overall_progress}%</span>
                </div>
                <Progress value={comp.overall_progress} className="h-2" />

                {/* ContinueLearningButton — §10.3 */}
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full mt-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/my-learning/${comp.competency_id}`);
                  }}
                >
                  {comp.overall_progress > 0 ? 'Continue Learning' : 'Start Learning'}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {competencies.length === 0 && (
        <Card className="text-center py-12">
          <CardContent>
            <BookOpen className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
              No competencies assigned yet. Contact your manager.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
