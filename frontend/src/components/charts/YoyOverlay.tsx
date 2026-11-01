import { useMemo } from 'react'

import { EChart } from '@/components/charts/EChart'
import { yoyOption } from '@/lib/cycle-options'

export function YoyOverlay(props: Parameters<typeof yoyOption>[0]) {
  const { years, colors } = props
  const option = useMemo(() => yoyOption({ years, colors }), [years, colors])
  return (
    <EChart
      option={option}
      label="Year-over-year overlay, each year from its first close"
      testId="yoy-overlay"
      className="h-[min(60vh,520px)] min-h-[340px]"
    />
  )
}
