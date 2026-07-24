/**
 * Post-session summary with score, mastery, skills improved, and feedback.
 * §10.3 — SessionSummaryCard: final score, mastery level, skills improved, feedback highlights
 */
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Trophy, Clock, MessageSquare, TrendingUp, ArrowRight, Loader2 } from 'lucide-react';
import { MasteryBadge } from '@/components/session/MasteryBadge';
import { SessionScoreBar } from '@/components/session/SessionScoreBar';
import { getSessionSummary, type SessionSummary } from '@/api/sessions';

export default function SessionComplete() {
  const { id: sessionId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    getSessionSummary(sessionId)
      .then(setSummary)
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading || !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const formatDuration = (secs: number) => {
    const minutes = Math.floor(secs / 60);
    return `${minutes} min`;
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 py-8 animate-scale-in">
      {/* Header */}
      <div className="text-center space-y-2">
        <Trophy className="h-12 w-12 mx-auto text-amber-400" />
        <h1 className="text-2xl font-bold tracking-tight">Session Complete!</h1>
        <p className="text-muted-foreground font-medium">{summary.skill_name}</p>
      </div>

      {/* SessionSummaryCard — §10.3 */}
      <Card>
        <CardHeader>
          <CardTitle>Session Summary</CardTitle>
          <CardDescription>
            {new Date(summary.started_at).toLocaleDateString()} —{' '}
            {formatDuration(summary.duration_seconds)}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Final score bar */}
          <SessionScoreBar
            score={summary.final_score}
            label="Final Score"
          />

          {/* Mastery level */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Mastery Level</span>
            <MasteryBadge level={summary.mastery_level} size="lg" />
          </div>

          {/* Stats row */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="space-y-1">
              <Clock className="h-5 w-5 mx-auto text-muted-foreground" />
              <p className="text-lg font-semibold font-mono">
                {formatDuration(summary.duration_seconds)}
              </p>
              <p className="text-xs text-muted-foreground">Duration</p>
            </div>
            <div className="space-y-1">
              <MessageSquare className="h-5 w-5 mx-auto text-muted-foreground" />
              <p className="text-lg font-semibold font-mono">{summary.interaction_count}</p>
              <p className="text-xs text-muted-foreground">Interactions</p>
            </div>
            <div className="space-y-1">
              <TrendingUp className="h-5 w-5 mx-auto text-muted-foreground" />
              <p className="text-lg font-semibold font-mono">
                {summary.skills_improved?.length ?? 0}
              </p>
              <p className="text-xs text-muted-foreground">Skills Improved</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Skills improved */}
      {summary.skills_improved && summary.skills_improved.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Skills Improved</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {summary.skills_improved.map((skill) => (
                <li
                  key={skill}
                  className="flex items-center gap-2 text-sm text-emerald-400 font-medium"
                >
                  <TrendingUp className="h-4 w-4" />
                  {skill}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Feedback highlights */}
      {summary.feedback_highlights && summary.feedback_highlights.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Feedback</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {summary.feedback_highlights.map((fb, idx) => (
                <li key={idx} className="text-sm text-muted-foreground">
                  • {fb}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Navigation */}
      <div className="flex gap-3 justify-center">
        <Button variant="outline" onClick={() => navigate('/my-learning')}>
          Back to My Learning
        </Button>
        <Button onClick={() => navigate('/my-learning')}>
          Continue Learning <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
