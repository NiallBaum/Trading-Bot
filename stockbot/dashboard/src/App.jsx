import { useEffect, useState } from 'react'

const DATA_URL = `${import.meta.env.BASE_URL}dashboard_data.json`

function fmtMoney(n) {
  return `£${Number(n).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(n) {
  const sign = n > 0 ? '+' : ''
  return `${sign}${Number(n).toFixed(2)}%`
}

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(DATA_URL, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error(`Status ${res.status}`)
        return res.json()
      })
      .then(setData)
      .catch((err) => setError(err.message))
  }, [])

  if (error) {
    return (
      <div className="app">
        <div className="empty-state">
          Couldn't load dashboard_data.json ({error}). The bot hasn't run yet,
          or the file path doesn't match your repo's Pages base URL.
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="app">
        <div className="empty-state">Loading...</div>
      </div>
    )
  }

  const returnIsUp = data.total_return_pct >= 0

  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1>Swing Bot // Ledger</h1>
          <div className="ticker-strip">{data.tickers_watched?.join(' · ')}</div>
        </div>
        <div className="last-updated">Last run: {data.last_updated}</div>
      </header>

      <div className="stat-grid">
        <div className="stat">
          <div className="label">Equity</div>
          <div className="value">{fmtMoney(data.equity)}</div>
        </div>
        <div className="stat">
          <div className="label">Total Return</div>
          <div className={`value ${returnIsUp ? 'up' : 'down'}`}>{fmtPct(data.total_return_pct)}</div>
        </div>
        <div className="stat">
          <div className="label">Cash</div>
          <div className="value">{fmtMoney(data.cash_balance)}</div>
        </div>
        <div className="stat">
          <div className="label">Win Rate</div>
          <div className="value">{data.win_rate}%</div>
        </div>
        <div className="stat">
          <div className="label">Trades</div>
          <div className="value">{data.total_trades}</div>
        </div>
      </div>

      <section>
        <h2>Open Positions {data.open_positions?.length ? `(${data.open_positions.length})` : ''}</h2>
        {data.open_positions?.length ? (
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Entry</th>
                <th>Shares</th>
                <th>Stop-Loss</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {data.open_positions.map((p, i) => (
                <tr key={i}>
                  <td><span className="badge">{p.ticker}</span></td>
                  <td>{fmtMoney(p.entry_price)}</td>
                  <td>{Number(p.size).toFixed(4)}</td>
                  <td>{fmtMoney(p.stop_loss)}</td>
                  <td>{p.entry_time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">No open positions right now — waiting for an entry signal.</div>
        )}
      </section>

      <section>
        <h2>Recent Closed Trades</h2>
        {data.recent_closed_trades?.length ? (
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>P&amp;L</th>
                <th>Reason</th>
                <th>Closed</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_closed_trades.map((t, i) => (
                <tr key={i}>
                  <td><span className="badge">{t.ticker}</span></td>
                  <td>{fmtMoney(t.entry_price)}</td>
                  <td>{fmtMoney(t.exit_price)}</td>
                  <td className={t.pnl_gbp >= 0 ? 'pnl-up' : 'pnl-down'}>
                    {fmtMoney(t.pnl_gbp)} ({fmtPct(t.pnl_pct)})
                  </td>
                  <td>{t.reason}</td>
                  <td>{t.exit_time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">No trades closed yet.</div>
        )}
      </section>

      <section>
        <h2>Activity Log (Last Run)</h2>
        <div className="activity-log">
          {data.activity_log?.length
            ? data.activity_log.map((line, i) => <div key={i}>{line}</div>)
            : <div>No activity recorded.</div>}
        </div>
      </section>

      <div className="footer-note">
        Paper trading only — no real funds. Rules: EMA20 + RSI14 crossover entries,
        2% max risk per trade, 1.5% stop-loss. Starting balance {fmtMoney(data.starting_balance)}.
      </div>
    </div>
  )
}
