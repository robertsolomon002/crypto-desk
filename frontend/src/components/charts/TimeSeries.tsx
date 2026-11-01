import { useMemo } from 'react'

import { EChart } from '@/components/charts/EChart'
import { timeSeriesOption } from '@/lib/stats-options'

export function TimeSeriesChart({
  label,
  testId,
  className,
  ...props
}: Parameters<typeof timeSeriesOption>[0] & {
  label: string
  testId: string
  className?: string
}) {
  const { lines, colors, percent, min, max } = props
  const option = useMemo(
    () => timeSeriesOption({ lines, colors, percent, min, max }),
    [lines, colors, percent, min, max],
  )
  return <EChart option={option} label={label} testId={testId} className={className ?? 'h-64'} />
}
