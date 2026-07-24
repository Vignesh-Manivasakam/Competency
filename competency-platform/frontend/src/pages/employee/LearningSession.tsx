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
    <div className="h-screen flex flex-col bg-background animate-scale-in">
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
          <div className="flex items-center gap-1 text-sm text-muted-foreground tabular-nums font-mono">
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
        <div className="bg-destructive/10 text-destructive text-sm px-4 py-2 text-center font-medium">
          {error}
        </div>
      )}

      {/* Session complete overlay */}
      {isComplete && (
        <div className="bg-emerald-500/10 text-emerald-400 text-sm px-4 py-2 text-center font-medium border-b border-emerald-500/20">
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
