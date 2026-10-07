No copy edge was measurable on 2 days of data.

# Copy-trading backtest

Data: 611647 trades from 111417 wallets, 2026-10-05 15:53Z to 2026-10-07 18:36Z; prices for 2140 mints from recordings. Run time 76 s.

Each hour the wallets are ranked from the 48 h of trades before that hour (`traders.score_wallets` + `rank_wallets`, rules `pnl` and `realized`). Every buy a top-N wallet makes in the next hour is copied: entry at the recorded price 60 s after their buy, exit at the recorded price at buy time + horizon, minus 5 points of cost. "priced" = buys with a recorded price within 10 minutes of both ends; the rest are skipped (no recording yet, or the coin left the feed).

| rule | top N | buys copied | 1h priced | 1h mean % | 1h median % | 1h positive | 6h priced | 6h mean % | 6h median % | 6h positive |
|---|---|---|---|---|---|---|---|---|---|---|
| pnl | 5 | 619 | 359 | -13.0 | -23.6 | 28% | 76 | -11.9 | -39.5 | 18% |
| pnl | 10 | 1362 | 790 | -17.8 | -25.6 | 26% | 168 | -20.2 | -35.5 | 14% |
| pnl | 20 | 2431 | 1444 | -7.5 | -19.4 | 31% | 432 | -14.6 | -21.7 | 24% |
| realized | 5 | 984 | 647 | -18.5 | -22.5 | 25% | 154 | -22.5 | -22.0 | 13% |
| realized | 10 | 1818 | 1241 | -21.3 | -22.5 | 22% | 311 | -22.9 | -21.0 | 15% |
| realized | 20 | 2696 | 1815 | -10.4 | -18.3 | 26% | 513 | -15.1 | -21.0 | 23% |

Coverage: of the copied buys with an entry price and an exit inside the recordings, 434 of 2804 (15%) had no price at 1h; 1930 of 2590 (75%) had no price at 6h (the coin left the feed, or a recording gap). If those were mostly dying coins, the true means are worse than shown.

Recommendation: no copy edge measurable (every 6h mean is <= 0 after 5-point cost); keep ARENA_TRADERS_RANK=realized ARENA_SHADOW_LEADERS=10
