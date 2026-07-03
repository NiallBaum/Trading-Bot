# Swing Trading Bot — Paper Trading + Dashboard

Rule-based EMA20/RSI14 swing strategy, paper-traded across a basket of stocks,
with a live React dashboard. Runs automatically on GitHub Actions — free, no
server, no electricity cost on your end.

## What's in here

- `bot.py` — the trading logic. Runs once per invocation (no infinite loop),
  checks all tickers, manages positions, updates state.
- `state/` — created automatically. `trading_state.json` (portfolio state) and
  `trade_log.csv` (full trade history). Committed back to the repo by the
  Actions workflow after every run.
- `dashboard/` — a small React (Vite) app that reads `dashboard_data.json` and
  displays equity, open positions, recent trades, and the last run's log.
- `.github/workflows/trading_bot.yml` — runs `bot.py` every 30 minutes during
  US market hours on weekdays, commits results back to the repo.
- `.github/workflows/deploy_dashboard.yml` — builds the React app and deploys
  it to GitHub Pages, automatically, after every bot run.

## Setup (one-time, ~5 minutes)

1. **Create a new GitHub repository** (public — GitHub Pages + Actions free
   minutes are unlimited/generous on public repos).

2. **Upload all these files/folders**, keeping the folder structure exactly
   as-is (drag-and-drop into GitHub's web UI works fine, or use `git push` if
   you're comfortable with the CLI).

3. **Edit `dashboard/vite.config.js`** — change `YOUR_REPO_NAME` to your
   actual repo name. This must match exactly or the dashboard assets won't
   load on GitHub Pages.

4. **Enable GitHub Pages**: repo Settings → Pages → under "Build and
   deployment", set Source to **GitHub Actions** (not "Deploy from a branch").

5. **Enable Actions permissions**: repo Settings → Actions → General →
   under "Workflow permissions", select **Read and write permissions**
   (needed so the bot can commit its own results back to the repo).

6. **Trigger the first run manually**: go to the Actions tab → "Trading Bot"
   workflow → Run workflow. This creates the first `state/` data. Then run
   "Deploy Dashboard" the same way (or just push any small change — it
   triggers automatically after "Trading Bot" completes).

7. Your dashboard will be live at:
   `https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/`

After that, everything is automatic — the bot checks the market every 30
minutes on weekdays, commits its results, and the dashboard rebuilds itself.
Just open the URL whenever you want to check in.

## Configuration

Open `bot.py` and adjust the top section:
- `TICKERS` — the basket of stocks it watches.
- `STARTING_BALANCE_GBP` — your paper account size.
- `MAX_RISK_PCT` / `STOP_LOSS_PCT` — risk management rules (2% / 1.5% by default).

## Important notes

- **This is paper trading only.** No real broker or real money is connected.
  Nothing in this repo can place a real trade.
- Free-tier reality check: expect a handful of trades per month per ticker,
  not per day — the strategy is intentionally selective (see conversation
  history / prior explanation for why).
- GitHub Actions free tier gives generous free minutes/month on public repos,
  more than enough for this schedule. If you ever go private, check GitHub's
  current free-tier minutes before assuming the same schedule is free.
- If you want the schedule to cover UK/London-listed tickers' market hours
  too (08:00–16:30 UK time), widen the cron window in
  `.github/workflows/trading_bot.yml`.
