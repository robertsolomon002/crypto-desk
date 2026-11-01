import { useMemo } from 'react'

import { EChart } from '@/components/charts/EChart'
import type { ChartColors } from '@/lib/chart-colors'
import type { MatrixRow } from '@/lib/stats-data'
import { monthlyHeatmapOption } from '@/lib/stats-options'

export function MonthlyHeatmap({ matrix, colors }: { matrix: MatrixRow[]; colors: ChartColors }) {
  const option = useMemo(() => monthlyHeatmapOption(matrix, colors), [matrix, colors])
  // About 22 px per year row; the wrapper scrolls sideways on a phone instead of the page.
  const height = Math.max(240, matrix.length * 22 + 70)
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[620px]" style={{ height }}>
        <EChart
          option={option}
          label="Monthly returns heatmap, year by month"
          testId="monthly-heatmap"
          className="h-full"
        />
      </div>
    </div>
  )
}
