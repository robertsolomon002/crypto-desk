import { useSearchParams } from 'react-router'

/**
 * A view setting kept in the URL (`?anchor=bottom`), so it survives reloads and shared links like
 * the coin does. Unknown values fall back to the default, and the default is left out of the URL.
 */
export function useUrlState<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T,
): [T, (value: T) => void] {
  const [params, setParams] = useSearchParams()
  const raw = params.get(key)
  const value = allowed.includes(raw as T) ? (raw as T) : fallback
  return [
    value,
    (next) =>
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev)
          if (next === fallback) out.delete(key)
          else out.set(key, next)
          return out
        },
        { replace: true },
      ),
  ]
}
