# RESULTS_PHASE_1

| Idea | Query 1 | Query 2 | Query 3 | Avg latency | Data completeness | Stability |
|---|---|---|---|---|---|---|
| A | failed (0) | failed (0) | failed (0) | 464 ms | char>=3: 0 | stable |
| B | failed (0) | failed (0) | failed (0) | 376 ms | char>=3: 0 | stable |
| C | failed (0) | failed (0) | failed (0) | 6319 ms | char>=3: 0 | stable |
| D | failed (0) | failed (0) | failed (0) | 5934 ms | char>=3: 0 | stable |
| E | failed (0) | failed (0) | failed (0) | 343 ms | char>=3: 0 | stable |
| F | failed (0) | failed (0) | failed (0) | 10877 ms | char>=3: 0 | stable |
| G | failed (0) | failed (0) | failed (0) | 314 ms | char>=3: 0 | stable |
| H | failed (0) | failed (0) | failed (0) | 409 ms | char>=3: 0 | stable |

## Stable

- No stable product extraction method was observed from the current server IP.
- Every probe eventually hit Ozon antibot or access denied responses.

## Partial

- Idea D and F were only partially useful diagnostically.
- They exposed cookies and challenge behavior, but still produced zero products.

## Failed

- Ideas A, B, C, E, G and H did not extract products.
- The dominant diagnosis was `403 Antibot Challenge` or `Доступ ограничен`
  on both HTML and API endpoints.
