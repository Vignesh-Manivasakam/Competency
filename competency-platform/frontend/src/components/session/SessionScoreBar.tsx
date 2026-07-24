/**
 * Animated progress bar showing the current session score (0-100).
 * Updates in real-time via WebSocket state. §10.3
 */
import React from 'react';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface SessionScoreBarProps {
  score: number;
  maxScore?: number;
  label?: string;
  showPercentage?: boolean;
  className?: string;
}

export function SessionScoreBar({
  score,
  maxScore = 100,
  label = 'Session Score',
  showPercentage = true,
  className,
}: SessionScoreBarProps) {
  const percentage = Math.min(Math.round((score / maxScore) * 100), 100);

  const barColor =
    percentage >= 80
      ? '[&>div]:bg-emerald-500'
      : percentage >= 50
        ? '[&>div]:bg-amber-500'
        : '[&>div]:bg-rose-500';

  return (
    <div className={cn('space-y-1', className)}>
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground font-medium">{label}</span>
        {showPercentage && (
          <span className="font-semibold tabular-nums">{percentage}%</span>
        )}
      </div>
      <Progress
        value={percentage}
        className={cn('h-3 transition-all duration-700 ease-out', barColor)}
      />
    </div>
  );
}
