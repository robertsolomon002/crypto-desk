import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
  /** What broke, e.g. "This tab" or "The app". */
  label?: string
}

interface State {
  error: Error | null
}

/** Catches render errors. Route boundaries are keyed by path, so navigating away resets them. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // No user data or keys reach render errors; the stack helps when Rob reports a problem.
    console.error(error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="mx-auto my-12 max-w-md space-y-3 text-center">
        <p className="font-medium">{this.props.label ?? 'This part of the app'} hit an error.</p>
        <p className="text-sm text-muted-foreground">
          Try again. If it keeps happening, reload the page.
        </p>
        <Button variant="outline" size="sm" onClick={() => this.setState({ error: null })}>
          Try again
        </Button>
      </div>
    )
  }
}
