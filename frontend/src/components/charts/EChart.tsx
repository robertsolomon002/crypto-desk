import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

// Only the parts the Cycles, Stats and On-chain tabs use are registered, which keeps the lazy chunk small.
echarts.use([
  BarChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  AriaComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export type EChartOption = echarts.EChartsCoreOption

/**
 * One ECharts instance per mount. Each new option replaces the last one (`notMerge`), so series
 * removed by a toggle disappear; the chart follows its container's size.
 */
export function EChart({
  option,
  label,
  className,
  testId,
}: {
  option: EChartOption
  label: string
  className?: string
  testId?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const instance = echarts.init(el, null, { renderer: 'canvas' })
    chart.current = instance
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(el)
    return () => {
      observer.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true })
  }, [option])

  return (
    <div
      ref={ref}
      role="img"
      aria-label={label}
      data-testid={testId}
      className={cn('h-80 w-full', className)}
    />
  )
}
