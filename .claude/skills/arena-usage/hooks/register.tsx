import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { OwnLimit, PlanWindow, UsageAgent, UsageData } from '../types'

// Live usage and controls for the memecoin arena's Claude agents (python main.py serves the API).
const PANE = 'arena-usage'
const PORTS = ['http://127.0.0.1:8000', 'http://127.0.0.1:8011'] // the real arena, then the demo
const usage = atom({ plugin: 'arena-usage', key: 'usage' } as const, null)
const error = atom({ plugin: 'arena-usage', key: 'error' } as const, null)
const base = atom({ plugin: 'arena-usage', key: 'base' } as const, PORTS[0])
const busy = atom({ plugin: 'arena-usage', key: 'busy' } as const, false)
const own = atom({ plugin: 'arena-usage', key: 'own' } as const, [])

const COLORS: Record<string, string> = {
  opus: '#f7c548', sonnet: '#62c6ff', fable: '#ff9a62', haiku: '#5ee0d0', claude: '#e8875e',
  'sonnet-degen': '#ff6fd8', 'sonnet-skeptic': '#b6e35a', 'sonnet-scalper': '#c792ea',
}
const OK = '#59e3a7'
const WARN = '#f7c548'
const BAD = '#ff6b7a'
const MUTED = '#8f89b8'
const FRAME = '#4b3f8f'
const MODE_COLOR = { normal: OK, slow: WARN, paused: BAD } as const

const level = (pct: number) => (pct >= 80 ? BAD : pct >= 50 ? WARN : OK)
const usd = (n: number | null | undefined) =>
  n == null ? '–' : n < 0.1 ? `$${n.toFixed(3)}` : `$${n.toFixed(2)}`
const tok = (n: number | null | undefined) =>
  n == null ? '–' : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(Math.round(n))
const dur = (s: number) => {
  s = Math.max(0, Math.round(s))
  if (s < 60) return `${s}s`
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`
}
const blocks = (pct: number, width: number) => {
  const full = Math.max(0, Math.min(width, Math.round((pct / 100) * width)))
  return ['█'.repeat(full), '░'.repeat(width - full)]
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'arena-usage',
      description: 'Show the memecoin arena Claude usage pane (plan limits, slow down, pause, daily cap)',
    })

    await $.command.register({
      name: 'arena-reset-money',
      description: "Reset every arena agent to the starting cash: /arena-reset-money keep or wipe (the Claudes' journals)",
    })

    let opened = false // the pane opens on its own the first time the arena answers, so other projects stay quiet
    const poll = async () => {
      try {
        const mine = await $.session.usage()
        await update($, own, () => mine.rateLimits.map(r => ({ kind: r.kind, percentUsed: r.percentUsed, resetsAt: r.resetsAt })))
      } catch {
        // no reading of our own yet
      }
      const current = await read($, base)
      for (const url of [current, ...PORTS.filter(p => p !== current)]) {
        try {
          const r = await $.http.fetch(`${url}/api/usage`)
          if (!r.ok) continue
          const data = JSON.parse(r.text) as UsageData
          await update($, usage, () => data)
          await update($, error, () => null)
          await update($, base, () => url)
          const w = (k: string) => data.plan?.windows.find(x => x.kind === k)
          const five = w('five_hour'), week = w('seven_day')
          $.ui.status(
            `Arena${five ? ` 5h ${Math.round(five.pct)}%` : ''}${week ? `, week ${Math.round(week.pct)}%` : ''}, ${usd(data.spent_today)} today` +
              (data.mode !== 'normal' ? `, ${data.mode}` : ''),
          )
          if (!opened) {
            opened = true
            void $.ui.open({ id: PANE, title: 'Arena usage' })
          }
          return
        } catch {
          // try the next port
        }
      }
      await update($, error, () => "Can't reach the arena on port 8000 or 8011. Start it with python main.py.")
      $.ui.status(undefined)
    }

    void poll()
    $.clock.every(5000, () => void poll())

    return next(e)
  })

  on('command.run', { command: 'arena-usage' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Arena usage' })

    return { text: 'Arena usage pane opened.' }
  })

  on('command.run', { command: 'arena-reset-money' }, async ($, e) => {
    const choice = (e.args ?? '').trim().toLowerCase()
    if (choice !== 'keep' && choice !== 'wipe') {
      return {
        text:
          "This puts every arena agent back to the starting cash with no positions and archives the trades so far " +
          '(usage history and recordings are kept). Every Claude journal is backed up to a file either way.\n' +
          'Run /arena-reset-money keep to keep their journals, or /arena-reset-money wipe to clear them.',
      }
    }
    const url = await read($, base)
    try {
      const r = await $.http.fetch(`${url}/api/reset-money`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ journals: choice }),
      })
      const j = JSON.parse(r.text)
      if (!r.ok) return { text: `Reset failed: ${j.error ?? `HTTP ${r.status}`}` }
      return {
        text: `Money reset done: season ${j.season} archived, journals ${j.journals}` +
          (j.backup ? `, journals backed up to ${j.backup}.` : '.'),
      }
    } catch (err) {
      return { text: `Couldn't reach the arena at ${url}. Is python main.py running? (${String(err)})` }
    }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Input } = $.ui.resolve(e)
    const data = await read($, usage)
    const problem = await read($, error)
    const url = await read($, base)
    const working = await read($, busy)
    const mine = await read($, own)
    const cols = e.viewport?.columns ?? 100

    const send = async (body: Record<string, unknown>) => {
      await update($, busy, () => true)
      try {
        const r = await $.http.fetch(`${url}/api/llm/control`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        const parsed = JSON.parse(r.text)
        if (r.ok) {
          await update($, usage, () => parsed as UsageData)
          await update($, error, () => null)
          $.ui.toast(body.agent ? `${body.agent}: ${body.mode}` : body.mode ? `All Claudes: ${body.mode}` : 'Daily cap updated')
        } else {
          await update($, error, () => String(parsed.error ?? `HTTP ${r.status}`))
        }
      } catch (err) {
        await update($, error, () => `Control failed: ${String(err)}`)
      } finally {
        await update($, busy, () => false)
      }
    }

    if (!data) {
      return (
        <Box flexDirection="column" padding={1}>
          <Text bold>Arena usage</Text>
          <Text color={MUTED}>{problem ?? 'Connecting to the arena…'}</Text>
        </Box>
      )
    }

    const now = data.now
    // The arena's newest reading; this session's own reading fills in until the arena has made a call
    const fallback: PlanWindow[] = mine
      .filter((r: OwnLimit) => r.kind === 'five_hour' || r.kind === 'seven_day')
      .map((r: OwnLimit) => ({
        kind: r.kind, label: r.kind === 'five_hour' ? '5-hour limit' : 'Weekly limit', pct: r.percentUsed,
        resets_at: r.resetsAt ? Date.parse(r.resetsAt) / 1000 : null, burn_per_hour: null, full_at: null,
      }))
    const windows = data.plan?.windows?.length ? data.plan.windows : fallback
    const source = data.plan?.as_of
      ? `as of the arena's last call, ${dur(now - data.plan.as_of)} ago`
      : fallback.length ? "from this Claude Code session (the arena hasn't made a call yet)" : ''
    const barWidth = Math.max(12, Math.min(48, cols - 46))
    const pace = (w: PlanWindow) => {
      if (w.burn_per_hour == null) return 'Pace: measuring, needs 30 minutes of readings'
      if (w.burn_per_hour <= 0) return 'Pace: flat over the last few hours'
      const rate = `Pace +${w.burn_per_hour.toFixed(1)}% an hour`
      return w.full_at ? `${rate}, full in about ${dur(w.full_at - now)}` : `${rate}, won't reach 100% before it resets`
    }

    const capLine = data.cap == null
      ? 'No daily cap'
      : `Cap ${usd(data.cap)} a day, ${usd(data.spent_today)} used${data.capped ? ', reached: running slow' : ''}`
    const rows = [...data.agents].sort((a, b) => b.cost_total - a.cost_total)
    const col = (w: number, text: string, props: Record<string, unknown> = {}) => (
      <Box width={w} flexShrink={0}><Text wrap="truncate" {...props}>{text}</Text></Box>
    )
    const head = (w: number, text: string) => col(w, text, { color: MUTED })

    return (
      <Box flexDirection="column" paddingX={1} gap={1}>
        <Box flexDirection="column" borderStyle="round" borderColor={FRAME} paddingX={1}>
          <Box flexDirection="row" justifyContent="space-between" flexWrap="wrap">
            <Text bold>Claude plan limits</Text>
            <Text color={MUTED}>{source}</Text>
          </Box>
          {windows.length === 0 && (
            <Text color={MUTED}>No reading yet. It appears after the arena's next Claude call.</Text>
          )}
          {windows.map((w: PlanWindow) => {
            const [fill, rest] = blocks(w.pct, barWidth)
            return (
              <Box key={w.kind} flexDirection="column" marginTop={1}>
                <Box flexDirection="row">
                  {col(14, w.label, { bold: true })}
                  <Text color={level(w.pct)}>{fill}</Text>
                  <Text color={FRAME}>{rest}</Text>
                  <Box width={7} flexShrink={0} justifyContent="flex-end"><Text bold color={level(w.pct)}>{`${Math.round(w.pct)}%`}</Text></Box>
                  <Text color={MUTED}>{w.resets_at ? `  resets in ${dur(w.resets_at - now)}` : ''}</Text>
                </Box>
                <Box paddingLeft={14}><Text color={MUTED}>{pace(w)}</Text></Box>
              </Box>
            )
          })}
          {data.plan?.status && data.plan.status !== 'allowed' && (
            <Text color={BAD}>Claude reports your plan status as {data.plan.status}. The arena's calls may be refused.</Text>
          )}
        </Box>

        <Box flexDirection="column">
          <Box flexDirection="row" gap={3} flexWrap="wrap">
            {([
              ['Arena today', usd(data.spent_today)], ['24h', usd(data.spent_24h)], ['Total', usd(data.spent_total)],
              ['Week at this pace', data.projected_week == null ? 'measuring' : `~${usd(data.projected_week)}`],
            ] as const).map(([k, v]) => (
              <Box key={k} flexDirection="row" gap={1}><Text color={MUTED}>{k}</Text><Text bold>{v}</Text></Box>
            ))}
            <Text color={data.capped ? BAD : MUTED}>{capLine}</Text>
          </Box>
          {problem && <Text color={BAD}>{problem}</Text>}
        </Box>

        <Box flexDirection="row" gap={1} flexWrap="wrap" alignItems="center">
          <Text color={MUTED}>All Claudes</Text>
          {(['normal', 'slow', 'paused'] as const).map(m => (
            <Button key={`all-${m}`} hotkey={m[0]} variant={data.mode === m ? 'primary' : undefined}
              label={m === 'normal' ? 'Normal' : m === 'slow' ? `Slow (${data.slow_minutes} min)` : 'Pause'}
              onPress={() => void send({ mode: m })} />
          ))}
          <Input key="cap" label="Daily cap $" placeholder={data.cap == null ? 'none' : String(data.cap)}
            submitLabel="set cap" onSubmit={value => {
              const n = Number(value.replace('$', '').trim())
              if (value.trim() && Number.isFinite(n) && n >= 0) void send({ cap: n })
              else void update($, error, () => 'Type a dollar amount, like 5')
            }} />
          {data.cap != null && <Button key="nocap" label="Remove cap" onPress={() => void send({ cap: null })} />}
          {working && <Text color={MUTED}>working…</Text>}
        </Box>

        <Box flexDirection="column" borderStyle="round" borderColor={FRAME} paddingX={1}>
          <Box flexDirection="row">
            {head(17, 'Claude')}{head(15, 'State')}{head(10, 'Calls')}{head(9, 'Tok/call')}{head(9, '$/call')}
            {head(9, 'Total')}{head(16, 'Share of spend')}{head(11, 'Weekly/day')}{head(12, 'Mode')}
          </Box>
          {rows.map((a: UsageAgent) => {
            const color = COLORS[a.avatar] ?? '#c8d0e8'
            const state = a.thinking_since ? `thinking ${dur(now - a.thinking_since)}` : a.error ? 'last call failed' : a.mode
            const stateColor = a.thinking_since ? '#62f0ff' : a.error ? BAD : MODE_COLOR[a.mode]
            const share = data.spent_total > 0 ? a.cost_total / data.spent_total : 0
            const [fill, rest] = blocks(share * 100, 8)
            return (
              <Box key={a.name} flexDirection="column">
                <Box flexDirection="row" alignItems="center">
                  {col(17, a.name, { color, bold: true })}
                  {col(15, `● ${state}`, { color: stateColor })}
                  {col(10, `${a.calls}${a.calls_1h ? ` (${a.calls_1h}/h)` : ''}`)}
                  {col(9, tok(a.avg_tokens))}
                  {col(9, usd(a.avg_cost))}
                  {col(9, usd(a.cost_total), { bold: true })}
                  <Box width={16} flexShrink={0} flexDirection="row">
                    <Text color={color}>{fill}</Text><Text color={FRAME}>{rest}</Text>
                    <Text color={MUTED}>{` ${Math.round(share * 100)}%`}</Text>
                  </Box>
                  {col(11, a.est_weekly_pct_per_day == null ? '–' : `≈${a.est_weekly_pct_per_day.toFixed(1)}%`)}
                  {(['normal', 'slow', 'paused'] as const).map(m => (
                    <Button key={`${a.name}-${m}`} plain variant={a.override === m ? 'primary' : undefined}
                      label={m === 'normal' ? 'N' : m === 'slow' ? 'S' : 'P'}
                      onPress={() => void send({ mode: m, agent: a.name })} />
                  ))}
                </Box>
                {a.error && !a.thinking_since && <Text color={BAD} wrap="truncate">{`  ${a.error}`}</Text>}
              </Box>
            )
          })}
        </Box>

        <Text color={MUTED} wrap="wrap">
          Plan limits are your account's real figures, reported by Claude Code with each arena call; the pace counts everything on your account, not only the arena. Dollar figures are Claude Code's API-price estimates, a relative measure, not a bill. Weekly/day is each Claude's rough slice of the weekly pace, by its share of arena spend. Mode buttons: N normal, S slow, P pause.
        </Text>
      </Box>
    )
  })
}
