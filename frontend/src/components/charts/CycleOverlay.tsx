import { useMemo } from 'react'

import { EChart } from '@/components/charts/EChart'
import { cycleOverlayOption } from '@/lib/cycle-options'
import { ANCHOR_NAME } from '@/lib/cycles-data'

export function CycleOverlay(props: Parameters<typeof cycleOverlayOption>[0]) {
  const { paths, current, y, mode, colors } = props
  const option = useMemo(
    () => cycleOverlayOption({ paths, current, y, mode, colors }),
    [paths, current, y, mode, colors],
  )
  return (
    <EChart
      option={option}
      label={`Cycle overlay aligned by ${ANCHOR_NAME[mode]}`}
      testId="cycle-overlay"
      className="h-[min(60vh,520px)] min-h-[340px]"
    />
  )
}
