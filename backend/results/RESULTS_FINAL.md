# RESULTS_FINAL

## Phase 1 Summary

- HTML, sitemap and composer-api probes consistently returned
  challenge pages or `403`.
- Browser-based methods were useful only for diagnostics.
- They surfaced `abt_data` cookies and showed that Ozon
  never exposed product JSON from the current IP.

## Cascade Architecture

```text
cache
  |
  v
composer-api -> html -> browser XHR -> browser DOM
  -> browser cookies -> sitemap -> graceful degradation
                                  |
                                  v
                           product enrichment
```

## Iteration Metrics

| Iteration | Success rate | Full data rate | Avg latency ms |
|---|---|---|---|
| iter_1 | 0% | 0% | 12918 |
| iter_2 | 0% | 0% | 11484 |
| iter_3 | 0% | 0% | 11785 |

## Main Findings

- Ozon is protected on both `www.ozon.ru` and `api.ozon.ru`
  from the current server IP.
- Warm browser cookies (`abt_data`, `__Secure-ETC`) were not
  sufficient to turn subsequent curl or browser requests
  into product-bearing responses.
- The parser therefore prioritizes graceful degradation
  and explicit diagnostics over blind retries.

## Known Limitations

- No live query produced stable product extraction in this environment.
- Characteristics enrichment is implemented but not validated live,
  because search never reached product pages.

## Recommendations

- Re-run the same phase scripts from the team production VPS
  and compare Phase 1 artifacts.
- If the production IP is cleaner, keep browser XHR
  and composer-api probes as the primary search path.
- If the production IP is also blocked, move Ozon to a demo cache strategy
  and document the limitation explicitly.
