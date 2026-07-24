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
            <span className="text-emerald-400 font-medium">Connected</span>
          </>
        ) : (
          <>
            <WifiOff className="h-3 w-3 text-rose-500" />
            <span className="text-rose-400 font-medium">Reconnecting…</span>
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
                'max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm transition-all',
                msg.role === 'employee'
                  ? 'bg-primary text-primary-foreground rounded-br-sm'
                  : 'bg-card border text-card-foreground rounded-bl-sm'
              )}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              <span className="block text-[10px] opacity-60 mt-1 text-right font-mono">
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
            <div className="bg-card border rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1.5 items-center">
                <span className="w-2 h-2 bg-primary/70 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 bg-primary/70 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 bg-primary/70 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form
        onSubmit={handleSubmit}
        className="border-t p-4 flex gap-2 items-end bg-card"
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
