import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Markdown } from './Markdown'

// Model output is untrusted (Section 3.6): Markdown yes, raw HTML never.

describe('Markdown', () => {
  it('renders Markdown, tables included', () => {
    const { container } = render(
      <Markdown
        text={'**BTC** is up.\n\n| Cycle | Multiple |\n|---|---|\n| 2017 | 5.4x |\n\n- one\n- two'}
      />,
    )
    expect(container.querySelector('strong')).toHaveTextContent('BTC')
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '5.4x' })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('never renders raw HTML', () => {
    const { container } = render(
      <Markdown
        text={
          'Hi <script>window.hacked = 1</script><img src=x onerror="alert(1)"><b>bold</b>\n\n<iframe src="https://evil.test"></iframe>'
        }
      />,
    )
    expect(container.querySelector('script, iframe, img, b')).toBeNull()
    expect(container.innerHTML).not.toContain('onerror')
    expect((window as unknown as { hacked?: number }).hacked).toBeUndefined()
  })

  it('only links http(s), in a new tab without a referrer', () => {
    render(
      <Markdown text="[ok](https://coinmetrics.io) [bad](javascript:alert(1)) [data](data:text/html,x)" />,
    )
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', 'https://coinmetrics.io/')
    expect(links[0]).toHaveAttribute('target', '_blank')
    expect(links[0].getAttribute('rel')).toContain('noreferrer')
    expect(screen.getByText('bad').tagName).toBe('SPAN')
  })

  it('shows image alt text instead of loading images', () => {
    const { container } = render(<Markdown text="![a chart](https://tracker.test/pixel.png)" />)
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('[a chart]')).toBeInTheDocument()
  })
})
