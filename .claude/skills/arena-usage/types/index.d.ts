export type Mode = 'normal' | 'slow' | 'paused'

export type UsageAgent = {
  name: string
  model: string
  persona: string | null
  avatar: string
  mode: Mode
  override: Mode
  thinking_since: number | null
  next_run: number
  error: string | null
  calls: number
  errors: number
  calls_1h: number
  tokens_in: number
  tokens_out: number
  cache_read: number
  think_tok: number
  cost_total: number
  cost_24h: number
  cost_1h: number
  avg_cost: number | null
  avg_secs: number | null
  avg_tokens: number | null
  share_24h: number
  est_weekly_pct_per_day: number | null
}

export type PlanWindow = {
  kind: string
  label: string
  pct: number
  resets_at: number | null
  burn_per_hour: number | null
  full_at: number | null
}

export type UsageData = {
  now: number
  mode: Mode
  cap: number | null
  capped: boolean
  slow_minutes: number
  spent_today: number
  spent_24h: number
  spent_total: number
  projected_week: number | null
  plan: { as_of: number | null; status: string | null; windows: PlanWindow[] }
  agents: UsageAgent[]
}

export type OwnLimit = { kind: string; percentUsed: number; resetsAt?: string }

declare module 'claude-code' {
  interface PluginState {
    'arena-usage': {
      usage: UsageData | null
      error: string | null
      base: string
      busy: boolean
      own: OwnLimit[]
    }
  }
}
