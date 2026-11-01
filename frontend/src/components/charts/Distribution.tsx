import { useMemo } from 'react'

import { EChart } from '@/components/charts/EChart'
import type { ChartColors } from '@/lib/chart-colors'
import type { Distribution } from '@/lib/stats-data'
import { distributionOption } from '@/lib/stats-options'

export function DistributionChart({ data, colors }: { data: Distribution; colors: ChartColors }) {
  const option = useMemo(() => distributionOption(data, colors), [data, colors])
  return (
    <EChart
      option={option}
      label="Return distribution histogram with the latest period marked"
      testId="distribution"
      className="h-72"
    />
  )
}
