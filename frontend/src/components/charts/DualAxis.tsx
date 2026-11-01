import { useMemo } from 'react'

import { EChart } from '@/components/charts/EChart'
import { dualAxisOption } from '@/lib/onchain-options'

export function DualAxisChart({
  label,
  testId,
  className,
  ...props
}: Parameters<typeof dualAxisOption>[0] & {
  label: string
  testId: string
  className?: string
}) {
  const { left, right, bands, refLines, colors } = props
  const option = useMemo(
    () => dualAxisOption({ left, right, bands, refLines, colors }),
    [left, right, bands, refLines, colors],
  )
  return <EChart option={option} label={label} testId={testId} className={className ?? 'h-64'} />
}
