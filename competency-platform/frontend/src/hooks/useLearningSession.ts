/**
 * WebSocket hook for live learning sessions.
 * Implements §10.3.1 Listing 13 with additional message types from §8.8:
 *   Receive: tutor_message, content_delivered, mastery_updated, session_complete, error
 *   Send: employee_response, ping, pause_session
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '@/store/authStore';

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
    const token = useAuthStore.getState().accessToken || localStorage.getItem('access_token');
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
      try {
        const data: WSIncoming = JSON.parse(event.data);

        switch (data.type) {
          case 'tutor_message':
          case 'content_delivered':
            setMessages((prev) => [
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
      } catch (err) {
        console.error('Error parsing WS message:', err);
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

      setMessages((prev) => [
        ...prev,
        { role: 'employee', content, timestamp: new Date().toISOString() },
      ]);
      setIsTyping(true); // Tutor is now "thinking"
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
