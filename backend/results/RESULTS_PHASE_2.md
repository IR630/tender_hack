# RESULTS_PHASE_2

| Query | Status | Method | Products | Latency | Block reason |
|---|---|---|---|---|---|
| футболка мужская хлопок | blocked | - | 0 | 13363 ms | api_challenge |
| шины 205/55 R16 | blocked | - | 0 | 11450 ms | api_challenge |
| принтер HP LaserJet | blocked | - | 0 | 12031 ms | api_challenge |
| куртка зимняя женская | blocked | - | 0 | 11519 ms | api_challenge |
| летние шины 195/65 R15 | blocked | - | 0 | 11003 ms | api_challenge |
| МФУ Canon | blocked | - | 0 | 11729 ms | api_challenge |

## Notes

- The cascade is implemented and exercised against live Ozon endpoints.
- On the current IP, the parser degrades gracefully
  after repeated antibot detections.
- No query produced extractable products in Phase 2,
  so enrichment logic remained unverified live.
