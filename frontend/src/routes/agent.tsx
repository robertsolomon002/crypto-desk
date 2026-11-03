import { useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowUp,
  CheckCircle2,
  Database,
  KeyRound,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  Square,
  Trash2,
  Wrench,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Markdown } from '@/components/agent/Markdown'
import { QueryStatus } from '@/components/overview/Panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  ChatRequestError,
  describeArgs,
  modelOptions,
  previewAsOf,
  snapshotLink,
  STARTERS,
  streamChat,
  toolLabel,
  useConversation,
  useConversations,
  useDeleteConversation,
  applyEvent,
  nextTurnKey,
  turnsFromDetail,
  type DoneEvent,
  type ToolCall,
  type Turn,
} from '@/lib/agent'
import { formatDateTime } from '@/lib/format'
import { LABEL, useStoredKey } from '@/lib/keys'
import { useMe, useModels } from '@/lib/queries'
import { cn } from '@/lib/utils'

// The Agent tab (Stage 5.2): chat with the desk's analyst over `POST /api/agent/chat` (SSE). Every
// tool call shows as a card whose "View data" opens its exact snapshot in the Data tab. Answers
// are model output, rendered as sanitized Markdown (never raw HTML).

const MAX_CHARS = 4000

// --- Pieces -------------------------------------------------------------------------------------

function ToolCard({ call }: { call: ToolCall }) {
  const asOf = call.preview ? previewAsOf(call.preview) : null
  return (
    <div
      className="rounded-md border bg-muted/30 px-2.5 py-1.5 text-xs"
      data-testid="tool-card"
      aria-label={`Tool call: ${toolLabel(call.name)}`}
    >
      <div className="flex items-center gap-1.5">
        {call.ok === null ? (
          <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-label="Running" />
        ) : call.ok ? (
          <CheckCircle2 className="size-3.5 text-positive" aria-label="Done" />
        ) : (
          <XCircle className="size-3.5 text-negative" aria-label="Failed" />
        )}
        <Wrench className="size-3 text-muted-foreground" aria-hidden />
        <span className="font-medium">{toolLabel(call.name)}</span>
        <span className="font-mono text-muted-foreground">{call.name}</span>
        {call.snapshotId !== null && (
          <Link
            to={snapshotLink(call.snapshotId)}
            className="ml-auto inline-flex shrink-0 items-center gap-1 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            <Database className="size-3" aria-hidden /> View data
          </Link>
        )}
      </div>
      {(call.args || asOf) && (
        <p className="mt-0.5 text-muted-foreground">
          {call.args ? describeArgs(call.args) : `as of ${asOf}`}
        </p>
      )}
      {call.preview && (
        <p className="mt-0.5 line-clamp-2 font-mono break-all text-muted-foreground/80">
          {call.preview}
        </p>
      )}
    </div>
  )
}

function DataUsed({ tools }: { tools: ToolCall[] }) {
  const used = tools.filter((t) => t.snapshotId !== null)
  if (used.length === 0) return null
  return (
    <div className="border-t pt-1.5 text-xs text-muted-foreground" data-testid="data-used">
      <span className="font-medium text-foreground">Data used: </span>
      {used.map((t, i) => {
        const asOf = t.preview ? previewAsOf(t.preview) : null
        return (
          <span key={t.callId}>
            {i > 0 && ' · '}
            <Link
              to={snapshotLink(t.snapshotId as number)}
              className="underline underline-offset-2"
            >
              {toolLabel(t.name)}
            </Link>
            {asOf && ` (as of ${asOf})`}
          </span>
        )
      })}
    </div>
  )
}

function AnswerMeta({ done }: { done: DoneEvent }) {
  return (
    <p className="font-mono text-[11px] text-muted-foreground tabular-nums">
      {done.model} · {done.tool_calls} tool {done.tool_calls === 1 ? 'call' : 'calls'} ·{' '}
      {(done.tokens_in + done.tokens_out).toLocaleString('en-US')} tokens
      {done.cost_usd !== null && done.cost_usd !== undefined && ` · $${done.cost_usd.toFixed(4)}`}
    </p>
  )
}

function TurnView({ turn }: { turn: Turn }) {
  if (turn.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-secondary px-3 py-2 text-sm whitespace-pre-wrap">
          {turn.text}
        </div>
      </div>
    )
  }
  const thinking = turn.streaming && !turn.text && turn.tools.length === 0
  return (
    <article className="space-y-2" aria-label="Answer" aria-busy={turn.streaming || undefined}>
      {turn.tools.length > 0 && (
        <div className="space-y-1">
          {turn.tools.map((t) => (
            <ToolCard key={t.callId} call={t} />
          ))}
        </div>
      )}
      {thinking && (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" aria-hidden /> Thinking…
        </p>
      )}
      {turn.text && <Markdown text={turn.text} />}
      {turn.error && (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-negative">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {turn.error}
        </p>
      )}
      {turn.done?.limited && (
        <p className="text-xs text-muted-foreground">
          The agent used all its tool calls for this answer, so it may not have checked everything.
        </p>
      )}
      {turn.done?.truncated && (
        <p className="text-xs text-muted-foreground">
          This answer hit the length limit and was cut off. Ask for the rest.
        </p>
      )}
      {!turn.streaming && <DataUsed tools={turn.tools} />}
      {turn.done && <AnswerMeta done={turn.done} />}
    </article>
  )
}

function ConversationList({
  activeId,
  onPick,
  onNew,
}: {
  activeId: number | null
  onPick: (id: number) => void
  onNew: () => void
}) {
  const q = useConversations()
  const del = useDeleteConversation()
  const [confirm, setConfirm] = useState<number | null>(null)
  return (
    <nav aria-label="Conversations" className="space-y-2">
      <Button variant="outline" size="sm" className="w-full justify-start gap-1.5" onClick={onNew}>
        <MessageSquarePlus className="size-3.5" aria-hidden /> New chat
      </Button>
      {q.isPending || q.isError ? (
        <QueryStatus {...q} lines={4} />
      ) : q.data.length === 0 ? (
        <p className="px-1 text-xs text-muted-foreground">No conversations yet.</p>
      ) : (
        <ul className="space-y-0.5">
          {q.data.map((c) => (
            <li key={c.id} className="group flex items-center gap-1">
              <button
                type="button"
                onClick={() => onPick(c.id)}
                aria-current={c.id === activeId ? 'page' : undefined}
                className={cn(
                  'min-w-0 flex-1 rounded-md px-2 py-1 text-left text-sm hover:bg-muted',
                  c.id === activeId && 'bg-muted font-medium',
                )}
              >
                <span className="block truncate">{c.title || 'Untitled'}</span>
                <span className="block text-[11px] text-muted-foreground">
                  {formatDateTime(c.updated_at)}
                </span>
              </button>
              {confirm === c.id ? (
                <Button
                  variant="destructive"
                  size="sm"
                  className="h-6 px-1.5 text-xs"
                  onClick={() => {
                    del.mutate(c.id, { onSuccess: () => c.id === activeId && onNew() })
                    setConfirm(null)
                  }}
                >
                  Delete
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 opacity-60 group-hover:opacity-100"
                  aria-label={`Delete conversation ${c.title ?? c.id}`}
                  onClick={() => setConfirm(c.id)}
                >
                  <Trash2 className="size-3" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </nav>
  )
}

function NoKey() {
  return (
    <Card size="sm" className="mx-auto max-w-md gap-2 px-4 py-4 text-center">
      <KeyRound className="mx-auto size-5 text-muted-foreground" aria-hidden />
      <h2 className="text-sm font-semibold">Add your AI key to chat</h2>
      <p className="text-sm text-muted-foreground">
        The agent runs on your own key. One OpenRouter key takes about two minutes to set up, and
        you can give it a spending limit.
      </p>
      <div>
        <Button asChild size="sm">
          <Link to="/settings">Set up a key in Settings</Link>
        </Button>
      </div>
    </Card>
  )
}

// --- Page ---------------------------------------------------------------------------------------

export function AgentPage() {
  const [params, setParams] = useSearchParams()
  const convId = Number(params.get('c')) || null
  const [storedKey] = useStoredKey()
  const { data: me } = useMe()
  const isAdmin = me?.role === 'admin'
  const models = useModels()
  const client = useQueryClient()
  const detail = useConversation(convId)

  const options = useMemo(
    () => (storedKey ? modelOptions(storedKey.provider, models.data?.data, storedKey.model) : []),
    [storedKey, models.data],
  )
  const [model, setModel] = useState<string | null>(null)
  const chosenModel = model && options.includes(model) ? model : (options[0] ?? null)

  // The conversation being streamed into is shown from local state; any other from the API.
  const [live, setLive] = useState<{ convId: number | null; turns: Turn[] } | null>(null)
  const turns =
    live && live.convId === convId
      ? live.turns
      : convId !== null && detail.data
        ? turnsFromDetail(detail.data)
        : []
  const streaming = turns.some((t) => t.streaming)

  const [draft, setDraft] = useState('')
  const [showList, setShowList] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const last = turns[turns.length - 1]
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [turns.length, last?.text.length, last?.tools.length])
  useEffect(() => () => abortRef.current?.abort(), [])

  const canChat = storedKey !== null || isAdmin
  const usesServerKey = storedKey === null && isAdmin

  const pick = (id: number | null) => {
    if (streaming) abortRef.current?.abort()
    setShowList(false)
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        if (id === null) out.delete('c')
        else out.set('c', String(id))
        return out
      },
      { replace: id === null },
    )
  }

  const send = async (text: string) => {
    const message = text.trim()
    if (!message || streaming || !canChat) return
    setDraft('')
    const controller = new AbortController()
    abortRef.current = controller
    let target = convId
    const answerKey = nextTurnKey()
    setLive({
      convId,
      turns: [
        ...turns,
        { key: nextTurnKey(), role: 'user', text: message, tools: [] },
        { key: answerKey, role: 'assistant', text: '', tools: [], streaming: true },
      ],
    })
    const update = (fn: (t: Turn) => Turn) =>
      setLive((prev) =>
        prev ? { ...prev, turns: prev.turns.map((t) => (t.key === answerKey ? fn(t) : t)) } : prev,
      )
    try {
      await streamChat(
        { message, conversationId: convId, key: storedKey, model: chosenModel },
        (e) => {
          if (e.event === 'conversation') {
            if (target === null) {
              target = e.data.id
              setLive((prev) => (prev ? { ...prev, convId: e.data.id } : prev))
              setParams(
                (prev) => {
                  const out = new URLSearchParams(prev)
                  out.set('c', String(e.data.id))
                  return out
                },
                { replace: true },
              )
            }
            client.invalidateQueries({ queryKey: ['agent', 'conversations'] })
            return
          }
          update((t) => applyEvent(t, e))
        },
        controller.signal,
      )
      update((t) =>
        t.streaming ? { ...t, streaming: false, error: t.error ?? 'The answer ended early.' } : t,
      )
    } catch (err) {
      const message = controller.signal.aborted
        ? 'Stopped.'
        : err instanceof ChatRequestError
          ? err.message
          : "Couldn't reach the server. Check your connection and try again."
      update((t) => ({ ...t, streaming: false, error: message }))
    } finally {
      abortRef.current = null
      client.invalidateQueries({ queryKey: ['agent', 'conversations'] })
      if (target !== null) client.invalidateQueries({ queryKey: ['agent', 'conversation', target] })
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(draft)
    }
  }

  const list = (
    <ConversationList
      activeId={convId}
      onPick={(id) => pick(id)}
      onNew={() => {
        pick(null)
        setLive(null)
      }}
    />
  )

  return (
    <div className="mx-auto grid max-w-7xl gap-4 lg:grid-cols-[15rem_1fr]">
      <aside className="hidden lg:block">{list}</aside>

      <section className="flex min-h-[70vh] min-w-0 flex-col gap-3" aria-labelledby="agent-title">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1 lg:hidden"
            aria-expanded={showList}
            onClick={() => setShowList((s) => !s)}
          >
            <PanelLeft className="size-3.5" aria-hidden /> Conversations
          </Button>
          <h1 id="agent-title" className="text-sm font-semibold">
            Agent
          </h1>
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            {storedKey ? (
              <label className="flex items-center gap-1">
                <span>{LABEL[storedKey.provider]}</span>
                <select
                  aria-label="Model"
                  value={chosenModel ?? ''}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={streaming}
                  className="h-7 max-w-52 rounded-md border bg-card px-1 font-mono text-xs text-foreground"
                >
                  {options.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            ) : usesServerKey ? (
              <Badge variant="outline" title="Rob's server key, capped at $8 a month">
                Server key · capped
              </Badge>
            ) : null}
          </div>
        </div>

        {showList && <div className="rounded-lg border p-2 lg:hidden">{list}</div>}

        {!canChat && me ? (
          <NoKey />
        ) : (
          <>
            <div className="flex-1 space-y-4" aria-live="polite">
              {convId !== null && !live && (detail.isPending || detail.isError) && (
                <QueryStatus {...detail} lines={4} />
              )}
              {turns.length === 0 && (convId === null || detail.data) && (
                <div className="mx-auto max-w-lg space-y-3 py-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    Ask about prices, levels, cycles, seasonality, on-chain or macro. Every number
                    comes from a tool you can open in the Data tab.
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {STARTERS.map((s) => (
                      <Button
                        key={s}
                        variant="outline"
                        size="sm"
                        className="h-auto py-1.5 text-left whitespace-normal"
                        onClick={() => void send(s)}
                      >
                        {s}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              {turns.map((t) => (
                <TurnView key={t.key} turn={t} />
              ))}
              <div ref={endRef} />
            </div>

            <form
              className="sticky bottom-14 space-y-1 bg-background pb-1 md:bottom-0"
              onSubmit={(e) => {
                e.preventDefault()
                void send(draft)
              }}
            >
              <div className="flex items-end gap-2 rounded-lg border bg-card p-1.5 focus-within:ring-1 focus-within:ring-ring">
                <textarea
                  aria-label="Ask the agent"
                  placeholder="Ask about BTC, ETH, SOL or the watchlist…"
                  value={draft}
                  maxLength={MAX_CHARS}
                  rows={2}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  className="min-h-10 flex-1 resize-none bg-transparent px-1.5 py-1 text-sm outline-none"
                />
                {streaming ? (
                  <Button
                    type="button"
                    size="icon"
                    variant="outline"
                    aria-label="Stop"
                    onClick={() => abortRef.current?.abort()}
                  >
                    <Square className="size-3.5" />
                  </Button>
                ) : (
                  <Button type="submit" size="icon" aria-label="Send" disabled={!draft.trim()}>
                    <ArrowUp className="size-4" />
                  </Button>
                )}
              </div>
              <p className="px-1 text-[11px] text-muted-foreground">
                Enter to send, Shift+Enter for a new line. Answers can be wrong; check the data. Not
                financial advice.
              </p>
            </form>
          </>
        )}
      </section>
    </div>
  )
}
