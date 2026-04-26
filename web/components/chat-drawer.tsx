"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  Bot,
  Database,
  Loader2,
  MessageSquare,
  Send,
  User,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ChatMatch, ChatStatus, ChatTurn } from "@/lib/types";
import { cn } from "@/lib/utils";

type UiMessage = ChatTurn & {
  id: string;
  matches?: ChatMatch[];
  status?: ChatStatus;
  usedModel?: string;
};

const STATUS_LABEL: Record<ChatStatus, string> = {
  found: "Match",
  partial: "Related",
  not_found: "No match",
  empty: "Empty",
  model_unavailable: "Local",
};

const STATUS_CLASS: Record<ChatStatus, string> = {
  found: "tag-success",
  partial: "tag-warning",
  not_found: "tag",
  empty: "tag",
  model_unavailable: "tag-accent",
};

function messageId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function ChatDrawer() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<UiMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Pregúntame por una funcionalidad y la compararé con la memoria local del proyecto.",
    },
  ]);
  const [loading, setLoading] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading, open]);

  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(() => inputRef.current?.focus(), 120);
    return () => window.clearTimeout(id);
  }, [open]);

  const submit = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const history = messages
      .filter((msg) => msg.id !== "welcome")
      .slice(-6)
      .map(({ role, content }) => ({ role, content }));

    const userMessage: UiMessage = {
      id: messageId(),
      role: "user",
      content: text,
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.chat(text, history);
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: "assistant",
          content: res.answer,
          matches: res.matches,
          status: res.status,
          usedModel: res.used_model,
        },
      ]);
    } catch (err) {
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: "assistant",
          content:
            err instanceof Error
              ? `No he podido consultar el backend: ${err.message}`
              : "No he podido consultar el backend.",
          status: "not_found",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submit();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          title="Open feature chat"
          aria-label="Open feature chat"
          className="fixed left-0 top-1/2 z-40 flex h-28 w-10 -translate-y-1/2 items-center justify-center gap-2 border border-l-0 border-rule2 bg-ink text-paper shadow-rule transition-colors hover:bg-graphite"
        >
          <span className="flex rotate-180 items-center gap-2 [writing-mode:vertical-rl]">
            <MessageSquare size={15} />
            <span className="font-mono text-meta">Chat</span>
          </span>
        </button>
      )}

      {open && (
        <div
          className="fixed inset-0 z-40 bg-ink/15 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-screen w-[min(430px,calc(100vw-16px))] flex-col border-r border-rule bg-paper shadow-2xl transition-transform duration-200",
          open ? "translate-x-0" : "-translate-x-full"
        )}
        aria-hidden={!open}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-rule px-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded bg-ink text-paper">
              <Bot size={16} />
            </span>
            <div className="min-w-0">
              <div className="font-serif text-lead leading-6">Feature chat</div>
              <div className="font-mono text-meta text-muted">
                Local project memory
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            title="Close"
            aria-label="Close feature chat"
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded border border-rule2 text-muted transition-colors hover:bg-surface hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>

        <div
          ref={scrollerRef}
          className="flex-1 space-y-4 overflow-y-auto px-4 py-5"
        >
          {messages.map((message) => (
            <ChatBubble key={message.id} message={message} />
          ))}
          {loading && (
            <div className="flex items-center gap-2 text-meta text-muted">
              <Loader2 size={14} className="animate-spin" />
              Thinking
            </div>
          )}
        </div>

        <form onSubmit={onSubmit} className="border-t border-rule bg-paper p-4">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              maxLength={2000}
              placeholder="¿Está hecho el login con JWT?"
              className="input max-h-32 min-h-12 resize-none"
              disabled={loading}
            />
            <button
              type="submit"
              title="Send"
              aria-label="Send message"
              disabled={!input.trim() || loading}
              className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded bg-ink text-paper transition-colors hover:bg-graphite disabled:cursor-not-allowed disabled:bg-rule2 disabled:text-muted"
            >
              {loading ? (
                <Loader2 size={17} className="animate-spin" />
              ) : (
                <Send size={17} />
              )}
            </button>
          </div>
        </form>
      </aside>
    </>
  );
}

function ChatBubble({ message }: { message: UiMessage }) {
  const assistant = message.role === "assistant";
  const Icon = assistant ? Bot : User;

  return (
    <div
      className={cn(
        "flex gap-3",
        assistant ? "justify-start" : "justify-end"
      )}
    >
      {assistant && (
        <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded border border-rule2 bg-surface text-muted">
          <Icon size={14} />
        </span>
      )}
      <div className={cn("min-w-0 max-w-[84%]", !assistant && "order-first")}>
        <div
          className={cn(
            "rounded border px-3 py-2 text-body",
            assistant
              ? "border-rule bg-surface text-ink"
              : "border-ink bg-ink text-paper"
          )}
        >
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>

        {assistant && message.status && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className={cn("tag", STATUS_CLASS[message.status])}>
              {STATUS_LABEL[message.status]}
            </span>
            {message.usedModel && (
              <span className="font-mono text-meta text-muted">
                {message.usedModel}
              </span>
            )}
          </div>
        )}

        {assistant && message.matches && message.matches.length > 0 && (
          <div className="mt-3 border border-rule bg-paper">
            <div className="flex items-center gap-2 border-b border-rule px-3 py-2">
              <Database size={14} className="text-muted" />
              <span className="font-mono text-meta text-muted">Evidence</span>
            </div>
            <div className="divide-y divide-rule">
              {message.matches.slice(0, 4).map((match) => (
                <EvidenceRow key={match.entity.id} match={match} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EvidenceRow({ match }: { match: ChatMatch }) {
  const percent = Math.round(match.score * 100);
  return (
    <div className="px-3 py-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-meta font-medium text-ink">
            {match.entity.name}
          </div>
          <div className="mt-0.5 truncate font-mono text-eyebrow uppercase text-muted">
            {match.entity.team} / {match.entity.source_type}
          </div>
        </div>
        <span className="shrink-0 font-mono text-meta text-muted">
          {percent}%
        </span>
      </div>
      <p className="mt-1 line-clamp-2 text-meta text-slate">
        {match.entity.description}
      </p>
    </div>
  );
}
