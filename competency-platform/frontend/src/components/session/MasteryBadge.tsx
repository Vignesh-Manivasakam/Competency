/**
 * Displays mastery level as a colored badge (0-5).
 * §10.3 — Used across session pages and profile.
 */
import React from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const MASTERY_CONFIG: Record<number, { label: string; color: string }> = {
  0: { label: 'Not Started', color: 'bg-slate-500/20 text-slate-300 border-slate-500/30' },
  1: { label: 'Awareness', color: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
  2: { label: 'Developing', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  3: { label: 'Proficient', color: 'bg-green-500/20 text-green-300 border-green-500/30' },
  4: { label: 'Advanced', color: 'bg-purple-500/20 text-purple-300 border-purple-500/30' },
  5: { label: 'Mastered', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
};

interface MasteryBadgeProps {
  level: number;
  size?: 'sm' | 'md' | 'lg';
  showLevel?: boolean;
}

export function MasteryBadge({ level, size = 'md', showLevel = true }: MasteryBadgeProps) {
  const config = MASTERY_CONFIG[Math.min(Math.max(level, 0), 5)] ?? MASTERY_CONFIG[0];
  const sizeClass = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  }[size];

  return (
    <Badge variant="outline" className={cn(config.color, sizeClass, 'font-medium')}>
      {showLevel && <span className="mr-1">{level}/5</span>}
      {config.label}
    </Badge>
  );
}
