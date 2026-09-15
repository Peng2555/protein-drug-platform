import { onMounted, onUnmounted, toValue, watch, type MaybeRefOrGetter } from 'vue'

export interface PollingOptions {
  interval?: number
  immediate?: boolean
}

/**
 * Runs once on mount and polls only while enabled.
 * The timer is always replaced when the enabled state changes.
 */
export function usePolling(
  task: () => void | Promise<void>,
  enabled: MaybeRefOrGetter<boolean>,
  options: PollingOptions = {},
) {
  const interval = options.interval ?? 5000
  let timer: ReturnType<typeof setInterval> | null = null

  function stop() {
    if (timer) clearInterval(timer)
    timer = null
  }

  function sync() {
    stop()
    if (toValue(enabled)) timer = setInterval(() => void task(), interval)
  }

  async function refresh() {
    await task()
    sync()
  }

  watch(() => toValue(enabled), sync)
  onMounted(async () => {
    if (options.immediate !== false) await refresh()
    else sync()
  })
  onUnmounted(stop)

  return { refresh, restart: sync, stop }
}
