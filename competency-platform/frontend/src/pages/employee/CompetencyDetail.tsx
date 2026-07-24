/**
 * Skill-level detail for a competency with learning path visualizer.
 * §10.3 — SkillProgressList, LearningPathVisualizer, StartSkillSessionButton
 */
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ArrowLeft, Play, Lock, CheckCircle2, Loader2 } from 'lucide-react';
import { MasteryBadge } from '@/components/session/MasteryBadge';
import {
  getCompetencySkills,
  getLearningPath,
  startSession,
  type SkillProgress,
  type LearningPathNode,
} from '@/api/sessions';

export default function CompetencyDetail() {
  const { competencyId } = useParams<{ competencyId: string }>();
  const navigate = useNavigate();
  const [skills, setSkills] = useState<SkillProgress[]>([]);
  const [path, setPath] = useState<LearningPathNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [startingSkill, setStartingSkill] = useState<string | null>(null);

  useEffect(() => {
    if (!competencyId) return;
    Promise.all([
      getCompetencySkills(competencyId),
      getLearningPath(competencyId),
    ])
      .then(([s, p]) => {
        setSkills(s);
        setPath(p.sort((a, b) => a.order - b.order));
      })
      .finally(() => setLoading(false));
  }, [competencyId]);

  const handleStartSession = async (skillId: string) => {
    setStartingSkill(skillId);
    try {
      const { session_id } = await startSession(skillId);
      navigate(`/sessions/${session_id}`);
    } catch {
      setStartingSkill(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-scale-in">
      <Button variant="ghost" onClick={() => navigate('/my-learning')}>
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to My Learning
      </Button>

      {/* LearningPathVisualizer — §10.3 */}
      <Card>
        <CardHeader>
          <CardTitle>Learning Path</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 overflow-x-auto pb-2">
            {path.map((node, idx) => (
              <React.Fragment key={node.skill_id}>
                <div
                  className={`flex flex-col items-center gap-1 min-w-[110px] p-3 rounded-lg border-2 transition-colors ${
                    node.is_current
                      ? 'border-primary bg-primary/10 shadow-sm'
                      : node.mastery_level >= 3
                        ? 'border-emerald-500/40 bg-emerald-500/10'
                        : 'border-muted bg-card'
                  }`}
                >
                  {node.mastery_level >= 5 ? (
                    <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                  ) : node.is_current ? (
                    <Play className="h-5 w-5 text-primary" />
                  ) : (
                    <Lock className="h-5 w-5 text-muted-foreground" />
                  )}
                  <span className="text-xs text-center font-medium line-clamp-2">
                    {node.skill_name}
                  </span>
                  <MasteryBadge level={node.mastery_level} size="sm" showLevel={false} />
                </div>
                {idx < path.length - 1 && (
                  <div className="h-0.5 w-8 bg-muted-foreground/30 shrink-0" />
                )}
              </React.Fragment>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* SkillProgressList — §10.3 */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Skills</h2>
        {skills.map((skill) => (
          <Card key={skill.skill_id}>
            <CardContent className="flex items-center justify-between py-4">
              <div className="flex-1 min-w-0 mr-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium truncate">{skill.skill_name}</span>
                  <MasteryBadge level={skill.mastery_level} size="sm" />
                </div>
                <p className="text-xs text-muted-foreground line-clamp-1">
                  {skill.description}
                </p>
                <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                  <span>{skill.session_count} sessions</span>
                  {skill.last_session_score !== null && (
                    <span>Last score: {skill.last_session_score}%</span>
                  )}
                </div>
                <Progress
                  value={(skill.mastery_level / 5) * 100}
                  className="h-1.5 mt-2"
                />
              </div>

              {/* StartSkillSessionButton — §10.3 */}
              <Button
                size="sm"
                disabled={!skill.prerequisites_met || startingSkill === skill.skill_id}
                onClick={() => handleStartSession(skill.skill_id)}
              >
                {startingSkill === skill.skill_id ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : !skill.prerequisites_met ? (
                  <>
                    <Lock className="mr-1 h-3 w-3" /> Locked
                  </>
                ) : (
                  <>
                    <Play className="mr-1 h-3 w-3" /> Start
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
