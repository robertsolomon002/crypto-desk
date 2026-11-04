import { useMutation } from '@tanstack/react-query'
import { Check, ExternalLink, Eye, EyeOff, KeyRound } from 'lucide-react'
import { useId, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { keyProblem, LABEL, maskKey, useStoredKey, type LlmKey, type Provider } from '@/lib/keys'
import { testKey, useModels, type KeyTestResult } from '@/lib/queries'
import { cn } from '@/lib/utils'

// The three steps per provider. Links checked against each provider's docs on 2026-11-01 (D42).
const STEPS: Record<Provider, { text: string; link: string; linkText: string }[]> = {
  openrouter: [
    {
      text: 'Sign up (Google or email).',
      link: 'https://openrouter.ai/',
      linkText: 'openrouter.ai',
    },
    {
      text: 'Add a few dollars of credit. $5 lasts most people months on the default model.',
      link: 'https://openrouter.ai/settings/credits',
      linkText: 'Credits',
    },
    {
      text: 'Create a key and give it a credit limit (for example $5), so it can never spend more.',
      link: 'https://openrouter.ai/keys',
      linkText: 'Keys',
    },
  ],
  anthropic: [
    {
      text: 'Sign in to the Claude Console.',
      link: 'https://platform.claude.com/',
      linkText: 'Console',
    },
    {
      text: 'Add credit and set a monthly spend limit on the Billing page.',
      link: 'https://platform.claude.com/settings/billing',
      linkText: 'Billing',
    },
    {
      text: 'Create an API key.',
      link: 'https://platform.claude.com/settings/keys',
      linkText: 'API keys',
    },
  ],
  openai: [
    {
      text: 'Create an API key in the OpenAI platform.',
      link: 'https://platform.openai.com/settings/organization/api-keys',
      linkText: 'API keys',
    },
    {
      text: 'Set a spend limit for your organization or project.',
      link: 'https://developers.openai.com/api/docs/guides/spend-limits',
      linkText: 'Spend limits guide',
    },
    {
      text: 'Check your usage limits.',
      link: 'https://platform.openai.com/settings/organization/limits',
      linkText: 'Limits',
    },
  ],
}

const PROVIDERS: Provider[] = ['openrouter', 'anthropic', 'openai']

function TestResult({ result, error }: { result?: KeyTestResult; error: unknown }) {
  if (error)
    return (
      <p role="status" className="text-sm text-negative">
        Couldn&apos;t run the test. Try again.
      </p>
    )
  if (!result) return null
  return (
    <p role="status" className={cn('text-sm', result.ok ? 'text-positive' : 'text-negative')}>
      {result.ok && <Check className="mr-1 inline size-4" aria-hidden />}
      {result.message}
    </p>
  )
}

function SavedKey({
  value,
  onChange,
  onForget,
}: {
  value: LlmKey
  onChange: () => void
  onForget: () => void
}) {
  const test = useMutation({ mutationFn: () => testKey(value.provider, value.key, value.model) })
  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Provider</dt>
        <dd>{LABEL[value.provider]}</dd>
        <dt className="text-muted-foreground">Key</dt>
        <dd className="font-mono" data-testid="saved-key">
          {maskKey(value.key)}
        </dd>
        <dt className="text-muted-foreground">Default model</dt>
        <dd className="font-mono">{value.model ?? 'provider default'}</dd>
      </dl>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>
          {test.isPending ? 'Testing…' : 'Test key'}
        </Button>
        <Button size="sm" variant="outline" onClick={onChange}>
          Change
        </Button>
        <Button size="sm" variant="ghost" onClick={onForget}>
          Forget key
        </Button>
      </div>
      <TestResult result={test.data} error={test.error} />
    </div>
  )
}

/** The LLM key setup (Decision 2): pick a provider, get a key with a limit, paste, test, save. */
export function KeyWizard() {
  const [stored, store] = useStoredKey()
  const [editing, setEditing] = useState(stored === null)
  const [provider, setProvider] = useState<Provider>(stored?.provider ?? 'openrouter')
  const [key, setKey] = useState('')
  const [show, setShow] = useState(false)
  const [model, setModel] = useState<string>(stored?.model ?? '')
  const [saved, setSaved] = useState<string | null>(null)
  const models = useModels()
  const info = models.data?.data.find((p) => p.id === provider)
  const problem = key ? keyProblem(provider, key) : null
  const test = useMutation({ mutationFn: () => testKey(provider, key.trim(), model || null) })
  const keyId = useId()
  const modelId = useId()

  const pick = (p: Provider) => {
    setProvider(p)
    setModel('')
    test.reset()
  }

  if (stored && !editing) {
    return (
      <div className="space-y-2">
        {saved && (
          <p role="status" className="text-sm">
            {saved}
          </p>
        )}
        <SavedKey
          value={stored}
          onChange={() => {
            setEditing(true)
            setSaved(null)
          }}
          onForget={() => {
            store(null)
            setEditing(true)
            setKey('')
            setSaved(null)
          }}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">1. Choose a provider</legend>
        <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Provider">
          {PROVIDERS.map((p) => (
            <button
              key={p}
              type="button"
              role="radio"
              aria-checked={provider === p}
              onClick={() => pick(p)}
              className={cn(
                'rounded-lg border p-3 text-left text-sm',
                provider === p ? 'border-foreground bg-muted/50' : 'hover:border-foreground/40',
              )}
            >
              <span className="flex items-center justify-between gap-2 font-medium">
                {LABEL[p]}
                {p === 'openrouter' && <Badge>Recommended</Badge>}
              </span>
              <span className="mt-1 block text-xs text-muted-foreground">
                {p === 'openrouter'
                  ? 'One key for Claude, GPT, Gemini and more, with a spending limit you set.'
                  : p === 'anthropic'
                    ? 'Claude models only.'
                    : 'GPT models only.'}
              </span>
            </button>
          ))}
        </div>
      </fieldset>

      <section className="space-y-2" aria-labelledby={`${keyId}-steps`}>
        <h3 id={`${keyId}-steps`} className="text-sm font-medium">
          2. Get a key with a limit
        </h3>
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          {STEPS[provider].map((s) => (
            <li key={s.link}>
              {s.text}{' '}
              <a
                href={s.link}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-0.5 underline"
              >
                {s.linkText}
                <ExternalLink className="size-3" aria-hidden />
              </a>
            </li>
          ))}
        </ol>
      </section>

      <section className="space-y-2" aria-labelledby={`${keyId}-paste`}>
        <h3 id={`${keyId}-paste`} className="text-sm font-medium">
          3. Paste it, test it, save it
        </h3>
        <div className="flex max-w-xl gap-1">
          <label htmlFor={keyId} className="sr-only">
            {LABEL[provider]} API key
          </label>
          <input
            id={keyId}
            type={show ? 'text' : 'password'}
            autoComplete="off"
            spellCheck={false}
            placeholder={
              provider === 'openrouter'
                ? 'sk-or-v1-…'
                : provider === 'anthropic'
                  ? 'sk-ant-…'
                  : 'sk-…'
            }
            value={key}
            onChange={(e) => {
              setKey(e.target.value)
              test.reset()
              setSaved(null)
            }}
            aria-invalid={problem ? true : undefined}
            aria-describedby={`${keyId}-hint`}
            className="h-8 min-w-0 flex-1 rounded-md border bg-card px-2 font-mono text-sm"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-8"
            aria-label={show ? 'Hide key' : 'Show key'}
            onClick={() => setShow((s) => !s)}
          >
            {show ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
          </Button>
        </div>
        <p
          id={`${keyId}-hint`}
          className={cn('text-xs', problem ? 'text-negative' : 'text-muted-foreground')}
        >
          {problem ??
            'Your key stays in this browser. It is sent only to our server with requests that need it, never stored or logged there.'}
        </p>

        {provider !== 'openai' && (
          <div className="flex max-w-xl flex-wrap items-center gap-2">
            <label htmlFor={modelId} className="text-xs text-muted-foreground">
              Default model
            </label>
            <input
              id={modelId}
              list={`${modelId}-choices`}
              value={model}
              placeholder={info?.default ?? ''}
              onChange={(e) => {
                setModel(e.target.value)
                test.reset()
              }}
              className="h-8 min-w-0 flex-1 rounded-md border bg-card px-2 font-mono text-sm"
            />
            <datalist id={`${modelId}-choices`}>
              {(info?.choices ?? []).map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!key || !!problem || test.isPending}
            onClick={() => test.mutate()}
          >
            <KeyRound aria-hidden /> {test.isPending ? 'Testing…' : 'Test key'}
          </Button>
          <Button
            size="sm"
            disabled={!key || !!problem}
            onClick={() => {
              const ok = store({ provider, key, model: model || null })
              setSaved(
                ok
                  ? 'Saved in this browser.'
                  : "This browser won't store it; it's kept for this visit only.",
              )
              setEditing(false)
            }}
          >
            Save in this browser
          </Button>
          {stored && (
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          )}
        </div>
        <TestResult result={test.data} error={test.error} />
        {saved && (
          <p role="status" className="text-sm">
            {saved}
          </p>
        )}
      </section>
    </div>
  )
}
