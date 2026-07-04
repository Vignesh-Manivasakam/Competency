# Frontend — Employee Portal

## Plan 19 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the complete Employee Portal frontend — all employee-facing pages for viewing assigned competencies, running live WebSocket-driven learning sessions with a chat interface, reviewing session summaries, and viewing personal skill profiles with radar charts. This plan delivers the five routes defined in §10.3 and the WebSocket session hook from §10.3.1 Listing 13.

### Prerequisites

- **Plan 15** (Session Graph + WebSocket) — WebSocket handler at `/api/v1/sessions/{id}/ws`
- **Plan 16** (Employee & Session APIs) — REST endpoints for employees, sessions, competencies
- **Plan 18** (Frontend Manager Portal) — Shared `AppLayout`, `apiClient` (Axios), `useAuthStore` (Zustand), Tailwind/shadcn setup, React Router configuration

### Spec References

| Section | Content |
|---------|---------|
| §10.3 | Employee Portal — Page and component breakdown (5 routes) |
| §10.3.1 | LearningSession Component (WebSocket) — Listing 13 |
| §8.8 | WebSocket message types: receive & send |
| §11 | Frontend project file structure |

---

### Files to Create/Modify

```
competency-platform/frontend/src/
├── api/
│   └── sessions.ts                    # Session & competency API client
├── hooks/
│   └── useLearningSession.ts          # WebSocket hook (Listing 13, extended)
├── pages/employee/
│   ├── MyLearning.tsx                 # /my-learning — competency cards + progress
│   ├── CompetencyDetail.tsx           # /my-learning/:competencyId — skill list
│   ├── LearningSession.tsx            # /sessions/:id — full-screen chat session
│   ├── SessionComplete.tsx            # /sessions/:id/complete — summary card
│   └── MyProfile.tsx                  # /my-profile — radar chart + history
├── components/session/
│   ├── ChatInterface.tsx              # Message list + input for session
│   ├── SessionScoreBar.tsx            # Real-time score progress bar
│   └── MasteryBadge.tsx               # Mastery level badge (0-5)
└── routes.tsx                         # (modify) Add employee routes
```

---

### Detailed Implementation Steps

#### Step 1: Session & Competency API Client

```typescript
// frontend/src/api/sessions.ts
/**
 * API client for employee-facing session and competency endpoints.
 * Consumes Plan 16 REST endpoints via the shared apiClient from Plan 18.
 *
 * §10.3 — All data fetching for the five employee routes.
 */
import { apiClient } from './client';

/* ---- Types ---- */

export interface CompetencyAssignment {
  id: string;
  competency_id: string;
  competency_name: string;
  description: string;
  total_skills: number;
  mastered_skills: number;
  overall_progress: number;        // 0-100
  current_mastery_level: number;   // 0-5
  assigned_at: string;
}

export interface SkillProgress {
  skill_id: string;
  skill_name: string;
  description: string;
  mastery_level: number;           // 0-5
  mastery_label: string;           // "Not Started" | "Awareness" | ... | "Mastered"
  last_session_score: number | null;
  session_count: number;
  prerequisites_met: boolean;
}

export interface SessionSummary {
  session_id: string;
  skill_name: string;
  final_score: number;
  mastery_level: number;
  mastery_label: string;
  skills_improved: string[];
  feedback_highlights: string[];
  duration_seconds: number;
  interaction_count: number;
  started_at: string;
  completed_at: string;
}

export interface ProfileData {
  employee_id: string;
  name: string;
  role: string;
  competencies: {
    competency_name: string;
    mastery_level: number;
  }[];
  mastery_history: {
    date: string;
    skill_name: string;
    old_level: number;
    new_level: number;
  }[];
  badges: {
    id: string;
    name: string;
    description: string;
    earned_at: string;
  }[];
}

export interface LearningPathNode {
  skill_id: string;
  skill_name: string;
  mastery_level: number;
  order: number;
  is_current: boolean;
  prerequisites: string[];
}

/* ---- API Functions ---- */

/** Fetch all competency assignments for the logged-in employee. §10.3 /my-learning */
export async function getMyCompetencies(): Promise<CompetencyAssignment[]> {
  const { data } = await apiClient.get<CompetencyAssignment[]>(
    '/api/v1/employees/me/competencies'
  );
  return data;
}

/** Fetch skill-level progress for a specific competency. §10.3 /my-learning/{id} */
export async function getCompetencySkills(
  competencyId: string
): Promise<SkillProgress[]> {
  const { data } = await apiClient.get<SkillProgress[]>(
    `/api/v1/employees/me/competencies/${competencyId}/skills`
  );
  return data;
}

/** Fetch the learning path graph for a competency. §10.3 /my-learning/{id} */
export async function getLearningPath(
  competencyId: string
): Promise<LearningPathNode[]> {
  const { data } = await apiClient.get<LearningPathNode[]>(
    `/api/v1/employees/me/competencies/${competencyId}/learning-path`
  );
  return data;
}

/** Start a new learning session for a skill. Returns the session object. */
export async function startSession(
  skillId: string
): Promise<{ session_id: string }> {
  const { data } = await apiClient.post<{ session_id: string }>(
    '/api/v1/sessions',
    { skill_id: skillId }
  );
  return data;
}

/** Fetch session summary after completion. §10.3 /sessions/{id}/complete */
export async function getSessionSummary(
  sessionId: string
): Promise<SessionSummary> {
  const { data } = await apiClient.get<SessionSummary>(
    `/api/v1/sessions/${sessionId}/summary`
  );
  return data;
}

/** Fetch employee profile data with radar chart info. §10.3 /my-profile */
export async function getMyProfile(): Promise<ProfileData> {
  const { data } = await apiClient.get<ProfileData>(
    '/api/v1/employees/me/profile'
  );
  return data;
}
```

#### Step 2: WebSocket Learning Session Hook (§10.3.1 Listing 13 — Extended)

```typescript
// frontend/src/hooks/useLearningSession.ts
/**
 * WebSocket hook for live learning sessions.
 * Implements §10.3.1 Listing 13 with additional message types from §8.8:
 *   Receive: tutor_message, content_delivered, mastery_updated, session_complete, error
 *   Send: employee_response, ping, pause_session
 */
import { useEffect, useRef, useState, useCallback } from 'react';

export interface SessionMessage {
  role: 'tutor' | 'employee';
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

interface WSIncoming {
  type: 'tutor_message' | 'content_delivered' | 'mastery_updated' | 'session_complete' | 'error';
  content?: string;
  current_score?: number;
  mastery_level?: number;
  error_message?: string;
  metadata?: Record<string, unknown>;
}

export function useLearningSession(sessionId: string) {
  const ws = useRef<WebSocket | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [currentScore, setCurrentScore] = useState(0);
  const [masteryLevel, setMasteryLevel] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);
  const responseStartRef = useRef<number>(0);
  const reconnectAttempts = useRef(0);
  const maxReconnects = 3;

  const connect = useCallback(() => {
    const token = localStorage.getItem('access_token');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.VITE_WS_HOST || 'localhost:8000';

    ws.current = new WebSocket(
      `${protocol}//${host}/api/v1/sessions/${sessionId}/ws?token=${token}`
    );

    ws.current.onopen = () => {
      setIsConnected(true);
      setError(null);
      reconnectAttempts.current = 0;
    };

    ws.current.onmessage = (event: MessageEvent) => {
      const data: WSIncoming = JSON.parse(event.data);

      switch (data.type) {
        case 'tutor_message':
        case 'content_delivered':
          setMessages(prev => [
            ...prev,
            {
              role: 'tutor',
              content: data.content ?? '',
              timestamp: new Date().toISOString(),
              metadata: data.metadata,
            },
          ]);
          if (data.current_score !== undefined) setCurrentScore(data.current_score);
          if (data.mastery_level !== undefined) setMasteryLevel(data.mastery_level);
          setIsTyping(false);
          // Mark when tutor message is received to compute response latency
          responseStartRef.current = Date.now();
          break;

        case 'mastery_updated':
          if (data.mastery_level !== undefined) setMasteryLevel(data.mastery_level);
          if (data.current_score !== undefined) setCurrentScore(data.current_score);
          break;

        case 'session_complete':
          setIsComplete(true);
          setIsTyping(false);
          break;

        case 'error':
          setError(data.error_message ?? 'An error occurred');
          break;
      }
    };

    ws.current.onclose = (event) => {
      setIsConnected(false);
      // Auto-reconnect on unexpected close (not session complete)
      if (!event.wasClean && !isComplete && reconnectAttempts.current < maxReconnects) {
        reconnectAttempts.current += 1;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 8000);
        setTimeout(connect, delay);
      }
    };

    ws.current.onerror = () => {
      setError('WebSocket connection error');
    };
  }, [sessionId, isComplete]);

  useEffect(() => {
    connect();
    // Heartbeat ping every 30s to keep connection alive
    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30_000);

    return () => {
      clearInterval(pingInterval);
      ws.current?.close();
    };
  }, [connect]);

  /** Send an employee response. Computes response latency automatically. §8.8 */
  const sendResponse = useCallback(
    (content: string) => {
      if (!ws.current || ws.current.readyState !== WebSocket.OPEN) return;
      const latencyMs = responseStartRef.current
        ? Date.now() - responseStartRef.current
        : 0;

      ws.current.send(
        JSON.stringify({
          type: 'employee_response',
          session_id: sessionId,
          content,
          response_latency_ms: latencyMs,
          timestamp: new Date().toISOString(),
        })
      );

      setMessages(prev => [
        ...prev,
        { role: 'employee', content, timestamp: new Date().toISOString() },
      ]);
      setIsTyping(true);  // Tutor is now "thinking"
    },
    [sessionId]
  );

  /** Pause the current session. §8.8 */
  const pauseSession = useCallback(() => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) return;
    ws.current.send(JSON.stringify({ type: 'pause_session', session_id: sessionId }));
  }, [sessionId]);

  return {
    messages,
    currentScore,
    masteryLevel,
    isComplete,
    isConnected,
    isTyping,
    error,
    sendResponse,
    pauseSession,
  };
}
```

#### Step 3: Reusable Session Components

```typescript
// frontend/src/components/session/MasteryBadge.tsx
/**
 * Displays mastery level as a colored badge (0-5).
 * §10.3 — Used across session pages and profile.
 */
import React from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const MASTERY_CONFIG: Record<number, { label: string; color: string }> = {
  0: { label: 'Not Started', color: 'bg-gray-100 text-gray-600' },
  1: { label: 'Awareness', color: 'bg-blue-100 text-blue-700' },
  2: { label: 'Developing', color: 'bg-yellow-100 text-yellow-700' },
  3: { label: 'Proficient', color: 'bg-green-100 text-green-700' },
  4: { label: 'Advanced', color: 'bg-purple-100 text-purple-700' },
  5: { label: 'Mastered', color: 'bg-emerald-100 text-emerald-800' },
};

interface MasteryBadgeProps {
  level: number;
  size?: 'sm' | 'md' | 'lg';
  showLevel?: boolean;
}

export function MasteryBadge({ level, size = 'md', showLevel = true }: MasteryBadgeProps) {
  const config = MASTERY_CONFIG[Math.min(Math.max(level, 0), 5)];
  const sizeClass = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  }[size];

  return (
    <Badge className={cn(config.color, sizeClass, 'font-medium')}>
      {showLevel && <span className="mr-1">{level}/5</span>}
      {config.label}
    </Badge>
  );
}
```

```typescript
// frontend/src/components/session/SessionScoreBar.tsx
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
        ? '[&>div]:bg-yellow-500'
        : '[&>div]:bg-red-500';

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
```

```typescript
// frontend/src/components/session/ChatInterface.tsx
/**
 * Chat UI for the learning session. Renders message list with auto-scroll
 * and input field. Drives the WebSocket via useLearningSession.
 * §10.3 — Core interaction component for /sessions/:id
 */
import React, { useState, useRef, useEffect, FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, Loader2, Wifi, WifiOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SessionMessage } from '@/hooks/useLearningSession';

interface ChatInterfaceProps {
  messages: SessionMessage[];
  isConnected: boolean;
  isTyping: boolean;
  isComplete: boolean;
  onSendMessage: (content: string) => void;
}

export function ChatInterface({
  messages,
  isConnected,
  isTyping,
  isComplete,
  onSendMessage,
}: ChatInterfaceProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || !isConnected || isComplete) return;
    onSendMessage(trimmed);
    setInput('');
    textareaRef.current?.focus();
  };

  // Submit on Enter (Shift+Enter for newline)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Connection status indicator */}
      <div className="flex items-center gap-2 px-4 py-2 border-b bg-muted/30 text-xs">
        {isConnected ? (
          <>
            <Wifi className="h-3 w-3 text-emerald-500" />
            <span className="text-emerald-600">Connected</span>
          </>
        ) : (
          <>
            <WifiOff className="h-3 w-3 text-red-500" />
            <span className="text-red-600">Reconnecting…</span>
          </>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={cn(
              'flex',
              msg.role === 'employee' ? 'justify-end' : 'justify-start'
            )}
          >
            <div
              className={cn(
                'max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
                msg.role === 'employee'
                  ? 'bg-primary text-primary-foreground rounded-br-md'
                  : 'bg-muted text-foreground rounded-bl-md'
              )}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              <span className="block text-[10px] opacity-50 mt-1 text-right">
                {new Date(msg.timestamp).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex gap-1 items-center">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form
        onSubmit={handleSubmit}
        className="border-t p-4 flex gap-2 items-end bg-background"
      >
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isComplete
              ? 'Session complete'
              : 'Type your response… (Enter to send)'
          }
          disabled={!isConnected || isComplete}
          className="resize-none min-h-[44px] max-h-[120px]"
          rows={1}
        />
        <Button
          type="submit"
          size="icon"
          disabled={!input.trim() || !isConnected || isComplete}
          className="shrink-0"
        >
          {isTyping ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </form>
    </div>
  );
}
```

#### Step 4: My Learning Page — `/my-learning`

```typescript
// frontend/src/pages/employee/MyLearning.tsx
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
        <p className="text-destructive text-sm">{error}</p>
        <Button variant="outline" className="mt-4" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
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
            <span className="text-sm font-semibold">{overallProgress}%</span>
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
            className="hover:shadow-md transition-shadow cursor-pointer"
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
                  <span>{comp.overall_progress}%</span>
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
```

#### Step 5: Competency Detail Page — `/my-learning/:competencyId`

```typescript
// frontend/src/pages/employee/CompetencyDetail.tsx
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
    <div className="space-y-6">
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
                  className={`flex flex-col items-center gap-1 min-w-[100px] p-3 rounded-lg border-2 transition-colors ${
                    node.is_current
                      ? 'border-primary bg-primary/5'
                      : node.mastery_level >= 3
                        ? 'border-emerald-300 bg-emerald-50'
                        : 'border-muted'
                  }`}
                >
                  {node.mastery_level >= 5 ? (
                    <CheckCircle2 className="h-5 w-5 text-emerald-500" />
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
        <h2 className="text-lg font-semibold">Skills</h2>
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
```

#### Step 6: Learning Session Page — `/sessions/:id` (Full-Screen)

```typescript
// frontend/src/pages/employee/LearningSession.tsx
/**
 * Full-screen live learning session with WebSocket chat.
 * §10.3 — LearningSession, ChatInterface, SessionScoreBar, SessionTimer, MasteryLevelBadge
 * §10.3.1 — WebSocket integration via useLearningSession hook
 */
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Pause, X, Clock } from 'lucide-react';
import { ChatInterface } from '@/components/session/ChatInterface';
import { SessionScoreBar } from '@/components/session/SessionScoreBar';
import { MasteryBadge } from '@/components/session/MasteryBadge';
import { useLearningSession } from '@/hooks/useLearningSession';

export default function LearningSession() {
  const { id: sessionId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const {
    messages,
    currentScore,
    masteryLevel,
    isComplete,
    isConnected,
    isTyping,
    error,
    sendResponse,
    pauseSession,
  } = useLearningSession(sessionId!);

  // SessionTimer — §10.3: Track elapsed time
  useEffect(() => {
    if (isComplete) return;
    const timer = setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [isComplete]);

  // Navigate to summary when session completes
  useEffect(() => {
    if (isComplete) {
      const timeout = setTimeout(
        () => navigate(`/sessions/${sessionId}/complete`),
        2000
      );
      return () => clearTimeout(timeout);
    }
  }, [isComplete, sessionId, navigate]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Top bar — Score, Mastery, Timer, Controls */}
      <header className="border-b px-4 py-3 flex items-center justify-between bg-card">
        <div className="flex items-center gap-4">
          <MasteryBadge level={masteryLevel} />
          <SessionScoreBar
            score={currentScore}
            className="w-48 hidden sm:block"
          />
        </div>

        <div className="flex items-center gap-3">
          {/* SessionTimer — §10.3 */}
          <div className="flex items-center gap-1 text-sm text-muted-foreground tabular-nums">
            <Clock className="h-4 w-4" />
            {formatTime(elapsedSeconds)}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={pauseSession}
            disabled={!isConnected || isComplete}
          >
            <Pause className="h-4 w-4 mr-1" /> Pause
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/my-learning')}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-destructive/10 text-destructive text-sm px-4 py-2 text-center">
          {error}
        </div>
      )}

      {/* Session complete overlay */}
      {isComplete && (
        <div className="bg-emerald-50 text-emerald-700 text-sm px-4 py-2 text-center font-medium">
          Session complete! Redirecting to summary…
        </div>
      )}

      {/* Chat area — fills remaining space */}
      <main className="flex-1 overflow-hidden">
        <ChatInterface
          messages={messages}
          isConnected={isConnected}
          isTyping={isTyping}
          isComplete={isComplete}
          onSendMessage={sendResponse}
        />
      </main>
    </div>
  );
}
```

#### Step 7: Session Complete Page — `/sessions/:id/complete`

```typescript
// frontend/src/pages/employee/SessionComplete.tsx
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
    <div className="max-w-2xl mx-auto space-y-6 py-8">
      {/* Header */}
      <div className="text-center space-y-2">
        <Trophy className="h-12 w-12 mx-auto text-yellow-500" />
        <h1 className="text-2xl font-bold">Session Complete!</h1>
        <p className="text-muted-foreground">{summary.skill_name}</p>
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
              <p className="text-lg font-semibold">
                {formatDuration(summary.duration_seconds)}
              </p>
              <p className="text-xs text-muted-foreground">Duration</p>
            </div>
            <div className="space-y-1">
              <MessageSquare className="h-5 w-5 mx-auto text-muted-foreground" />
              <p className="text-lg font-semibold">{summary.interaction_count}</p>
              <p className="text-xs text-muted-foreground">Interactions</p>
            </div>
            <div className="space-y-1">
              <TrendingUp className="h-5 w-5 mx-auto text-muted-foreground" />
              <p className="text-lg font-semibold">
                {summary.skills_improved.length}
              </p>
              <p className="text-xs text-muted-foreground">Skills Improved</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Skills improved */}
      {summary.skills_improved.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Skills Improved</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {summary.skills_improved.map((skill) => (
                <li
                  key={skill}
                  className="flex items-center gap-2 text-sm text-emerald-600"
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
      {summary.feedback_highlights.length > 0 && (
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
```

#### Step 8: My Profile Page — `/my-profile`

```typescript
// frontend/src/pages/employee/MyProfile.tsx
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
  const radarData = profile.competencies.map((c) => ({
    competency: c.competency_name,
    level: c.mastery_level,
    fullMark: 5,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
          <User className="h-8 w-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">{profile.name}</h1>
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
                  tick={{ fontSize: 12 }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 5]}
                  tick={{ fontSize: 10 }}
                  tickCount={6}
                />
                <Radar
                  name="Mastery"
                  dataKey="level"
                  stroke="#6366f1"
                  fill="#6366f1"
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
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" /> Mastery History
            </CardTitle>
          </CardHeader>
          <CardContent>
            {profile.mastery_history.length > 0 ? (
              <div className="relative space-y-4">
                {/* Vertical timeline line */}
                <div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-muted" />

                {profile.mastery_history.map((entry, idx) => (
                  <div key={idx} className="flex gap-4 relative">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center z-10 shrink-0">
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
                      <p className="text-xs text-muted-foreground mt-1">
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
            <CardTitle className="flex items-center gap-2">
              <Award className="h-5 w-5" /> Badges Earned
            </CardTitle>
          </CardHeader>
          <CardContent>
            {profile.badges.length > 0 ? (
              <div className="grid grid-cols-2 gap-3">
                {profile.badges.map((badge) => (
                  <div
                    key={badge.id}
                    className="flex flex-col items-center gap-2 p-4 border rounded-lg bg-muted/30 text-center"
                  >
                    <Award className="h-8 w-8 text-yellow-500" />
                    <span className="text-sm font-medium">{badge.name}</span>
                    <span className="text-xs text-muted-foreground line-clamp-2">
                      {badge.description}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
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
```

#### Step 9: Route Registration (Modify `routes.tsx`)

```typescript
// frontend/src/routes.tsx  (add employee routes to existing router)
/**
 * §11 — Employee routes added alongside manager routes from Plan 18.
 * Learning session uses a full-screen layout (no sidebar).
 */
import { lazy } from 'react';
import { RouteObject } from 'react-router-dom';
import AppLayout from '@/components/layout/AppLayout';

// Plan 18 — Manager pages (already registered)
const ManagerDashboard = lazy(() => import('@/pages/manager/Dashboard'));
// ... other manager imports from Plan 18

// Plan 19 — Employee pages
const MyLearning = lazy(() => import('@/pages/employee/MyLearning'));
const CompetencyDetail = lazy(() => import('@/pages/employee/CompetencyDetail'));
const LearningSession = lazy(() => import('@/pages/employee/LearningSession'));
const SessionComplete = lazy(() => import('@/pages/employee/SessionComplete'));
const MyProfile = lazy(() => import('@/pages/employee/MyProfile'));

export const employeeRoutes: RouteObject[] = [
  {
    // Employee pages inside shared layout (sidebar + topbar)
    element: <AppLayout role="employee" />,
    children: [
      { path: '/my-learning', element: <MyLearning /> },
      { path: '/my-learning/:competencyId', element: <CompetencyDetail /> },
      { path: '/sessions/:id/complete', element: <SessionComplete /> },
      { path: '/my-profile', element: <MyProfile /> },
    ],
  },
  {
    // Full-screen session — NO layout wrapper for immersive experience
    path: '/sessions/:id',
    element: <LearningSession />,
  },
];
```

---

### Verification Criteria

1. **My Learning page**: Displays assigned competencies as cards with progress bars, mastery badges, and "Continue Learning" buttons. Empty state renders when no assignments exist.
2. **Competency detail**: Shows skill list with mastery levels, session counts, and "Start" / "Locked" buttons based on prerequisite status. Learning path visualizer renders a horizontal node graph.
3. **WebSocket connection**: `useLearningSession` hook establishes WebSocket at `/api/v1/sessions/{id}/ws?token=...`, handles `onopen`, `onmessage`, `onclose`, `onerror` lifecycle events.
4. **Message exchange**: Employee can type a response, send via WebSocket (`employee_response` type), and receive tutor replies (`tutor_message` / `content_delivered`) rendered in the chat.
5. **Real-time updates**: `SessionScoreBar` updates smoothly as `current_score` changes. `MasteryBadge` reflects `mastery_level` from WebSocket state.
6. **Typing indicator**: Three-dot animation appears while waiting for tutor response between send and receive.
7. **Auto-reconnect**: On unexpected WebSocket close, hook retries up to 3 times with exponential backoff.
8. **Session complete flow**: On `session_complete` message, user sees banner and auto-navigates to `/sessions/{id}/complete`.
9. **Session summary**: Shows final score, mastery level, duration, interaction count, skills improved, and feedback highlights.
10. **Profile radar chart**: Recharts `RadarChart` renders all competencies on a 0-5 scale. Mastery history timeline and badges grid display correctly.
11. **Session timer**: Elapsed time displayed in `MM:SS` format, stops on session complete.
12. **Heartbeat ping**: WebSocket sends `ping` every 30 seconds to keep the connection alive.

### Notes & Gotchas

- **Full-screen session**: `LearningSession` renders without `AppLayout` — it uses `h-screen flex flex-col` for an immersive full-screen experience; other employee pages use the shared sidebar layout from Plan 18
- **Response latency**: Automatically computed as `Date.now() - responseStartRef.current` so the backend can use it for assessment scoring (§8.8)
- **WebSocket URL**: Protocol auto-selects `ws:` vs `wss:` based on page protocol; host is configurable via `VITE_WS_HOST` environment variable
- **Stale closure avoidance**: `sendResponse` and `pauseSession` are wrapped in `useCallback` with `[sessionId]` dependency to prevent stale WebSocket references
- **Token from localStorage**: Matches the auth pattern from Plan 18's `useAuthStore` — token is stored after login and read by the WebSocket hook
- **Recharts dependency**: `recharts` must be added to `package.json` (should already exist from Plan 18's manager dashboard charts)
- **Lazy loading**: All page components use `React.lazy()` + `Suspense` for code-splitting, keeping the initial bundle small
