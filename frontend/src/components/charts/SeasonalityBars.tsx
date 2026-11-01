import { useMemo } from 'react'

import { EChart } from '@/components/charts/EChart'
import type { ChartColors } from '@/lib/chart-colors'
import type { SummaryRow } from '@/lib/stats-data'
import { seasonalityBarsOption, type Stat } from '@/lib/stats-options'

export function SeasonalityBars({
  rows,
  labels,
  stat,
  colors,
  label,
  testId,
}: {
  rows: SummaryRow[]
  labels: string[]
  stat: Stat
  colors: ChartColors
  label: string
  testId: string
}) {
  const option = useMemo(
    () => seasonalityBarsOption(rows, labels, stat, colors),
    [rows, labels, stat, colors],
  )
  return <EChart option={option} label={label} testId={testId} className="h-56" />
}
