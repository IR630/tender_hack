import { FormEvent, useEffect, useRef, useState } from "react";

import { DEFAULT_REGION_ID, loadStoredRegion, RegionSelector } from "./components/RegionSelector";
import { SearchProgress } from "./components/SearchProgress";
import { SourceGroup } from "./components/SourceGroup";
import type {
  SearchGroup,
  SearchResponse,
  SearchTaskCreateResponse,
  SearchTaskStatusResponse,
} from "./types/search";
import { SEARCH_POLL_INTERVAL_MS } from "./types/search";

const SOURCE_ORDER = ["wildberries", "yandex_market", "ozon", "other"] as const;

const SOURCE_NAMES: Record<(typeof SOURCE_ORDER)[number], string> = {
  wildberries: "Wildberries",
  yandex_market: "Яндекс Маркет",
  ozon: "Ozon",
  other: "Другие",
};

const GRID_REVEAL_MS = 3000;

function orderGroups(groups: SearchResponse["groups"]) {
  return SOURCE_ORDER.map((source) => groups.find((group) => group.source === source)).filter(
    (group): group is NonNullable<typeof group> => Boolean(group),
  );
}

// Always render all four source slots in a fixed order; fill the ones that
// haven't returned yet with an empty placeholder so the 2×2 grid never reflows.
function buildFixedGroups(groups: SearchGroup[]): SearchGroup[] {
  const bySource = new Map(groups.map((group) => [group.source, group]));
  return SOURCE_ORDER.map(
    (source) =>
      bySource.get(source) ?? {
        source,
        display_name: SOURCE_NAMES[source],
        count: 0,
        min_price: null,
        domains: [],
        products: [],
        error: null,
        status: null,
      },
  );
}

function formatRub(price: number | null): string {
  if (price === null) {
    return "—";
  }
  return `${Math.round(price / 100).toLocaleString("ru-RU")} ₽`;
}

export default function App() {
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState(loadStoredRegion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [searchStarted, setSearchStarted] = useState(false);
  const [gridRevealed, setGridRevealed] = useState(false);
  const pollRef = useRef<number | null>(null);
  const revealRef = useRef<number | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
      if (revealRef.current !== null) {
        window.clearTimeout(revealRef.current);
      }
    };
  }, []);

  // once the spinner's 3s elapse and the grid reveals, bring the results
  // (stats strip + source blocks) up to the top of the viewport
  useEffect(() => {
    if (!gridRevealed) {
      return;
    }
    const target = resultsRef.current;
    if (!target) {
      return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }, [gridRevealed]);

  function stopPolling() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function pollTask(taskId: string) {
    const response = await fetch(`/api/search/${taskId}`);
    if (!response.ok) {
      throw new Error(`Poll error: ${response.status}`);
    }
    const payload = (await response.json()) as SearchTaskStatusResponse;
    setStatusMessage(payload.message ?? null);

    if (payload.groups.length > 0) {
      setResult((prev) =>
        prev
          ? { ...prev, groups: orderGroups(payload.groups) }
          : {
              query: {
                original: query.trim(),
                corrected: query.trim(),
                region,
                region_name: region,
                synonyms_used: [],
                took_ms: 0,
              },
              summary: { total_found: 0, min_price: null, median_price: null, max_price: null },
              groups: orderGroups(payload.groups),
            },
      );
    }

    if (payload.status === "completed" && payload.result) {
      stopPolling();
      setResult(payload.result);
      setLoading(false);
      setStatusMessage(null);
    }

    if (payload.status === "failed") {
      stopPolling();
      setLoading(false);
      throw new Error(payload.error ?? "Search failed");
    }
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }

    stopPolling();
    setLoading(true);
    setError(null);
    setResult(null);
    setStatusMessage("Запуск поиска…");

    // Strict reveal: spinner only for the first 3s, then the fixed 2×2 grid —
    // regardless of how fast (or slow) the sources come back.
    setSearchStarted(true);
    setGridRevealed(false);
    if (revealRef.current !== null) {
      window.clearTimeout(revealRef.current);
    }
    revealRef.current = window.setTimeout(() => setGridRevealed(true), GRID_REVEAL_MS);

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, region: region || DEFAULT_REGION_ID }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const { task_id } = (await response.json()) as SearchTaskCreateResponse;
      await pollTask(task_id);

      pollRef.current = window.setInterval(() => {
        pollTask(task_id).catch((pollError) => {
          stopPolling();
          setLoading(false);
          setError(pollError instanceof Error ? pollError.message : "Unknown error");
        });
      }, SEARCH_POLL_INTERVAL_MS);
    } catch (searchError) {
      stopPolling();
      setError(searchError instanceof Error ? searchError.message : "Unknown error");
      setResult(null);
      setLoading(false);
      setStatusMessage(null);
    }
  }

  const orderedGroups = result ? orderGroups(result.groups) : [];
  const summary = result?.summary;
  const hasSummary = Boolean(!loading && result && summary && summary.total_found > 0);
  const fixedGroups = buildFixedGroups(orderedGroups);
  const presentSources = new Set(orderedGroups.map((group) => group.source));
  const showGrid = searchStarted && gridRevealed;
  const loaderPhase: "centered" | "docked" | "hidden" = !searchStarted
    ? "hidden"
    : !gridRevealed
      ? "centered"
      : loading
        ? "docked"
        : "hidden";

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-rule bg-paper backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-baseline gap-2.5">
            <span className="text-base font-semibold tracking-display text-ink">Тендер-Поиск</span>
            <span className="hidden text-xs text-muted sm:inline">цены по Рунету</span>
          </div>
          <RegionSelector value={region} onChange={setRegion} />
        </div>
      </header>

      <main ref={mainRef} className="relative mx-auto w-full max-w-5xl flex-1 px-5 pb-20 pt-10 sm:pt-14">
        <section className="max-w-2xl">
          <h1 className="text-balance break-words font-display text-4xl font-medium leading-[1.08] tracking-display text-ink [overflow-wrap:anywhere] sm:text-5xl">
            Сравните цены на одной странице
          </h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-neutral">
            Один запрос — предложения с маркетплейсов и из Рунета, сгруппированные по источникам.
            С исправлением опечаток, синонимами и учётом региона доставки.
          </p>

          <form ref={formRef} onSubmit={handleSearch} className="mt-7 flex flex-col gap-2.5 sm:flex-row">
            <div className="relative flex-1">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Например: айфон 15 про 256"
                aria-label="Поисковый запрос"
                className="w-full rounded-input border border-rule-2 bg-paper px-4 py-3 text-ink outline-none transition-colors placeholder:text-muted hover:border-ink-2 focus-visible:border-ink focus-visible:ring-2 focus-visible:ring-focus/60"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="rounded-pill bg-accent px-7 py-3 font-medium text-accent-ink outline-none transition-transform duration-[120ms] ease-out hover:-translate-y-px active:translate-y-0 active:bg-ink-2 focus-visible:ring-2 focus-visible:ring-focus/60 focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
            >
              {loading ? "Ищем…" : "Найти"}
            </button>
          </form>
        </section>

        {error && (
          <p
            role="alert"
            className="mt-8 rounded-card border border-rule-2 bg-paper-2 px-4 py-3 text-sm text-ink-2"
          >
            Не удалось выполнить поиск: {error}
          </p>
        )}

        <SearchProgress
          mainRef={mainRef}
          formRef={formRef}
          phase={loaderPhase}
          query={query}
          statusMessage={statusMessage}
        />

        {showGrid && (
          <div ref={resultsRef} className="mt-12 scroll-mt-24 space-y-8">
            {hasSummary && summary && (
              <section className="border-y border-rule py-5">
                <dl className="flex flex-wrap items-end gap-x-10 gap-y-4">
                  <div>
                    <dt className="text-xs uppercase tracking-label text-muted">Найдено</dt>
                    <dd className="tnum mt-1 text-2xl font-medium text-ink">
                      {summary.total_found.toLocaleString("ru-RU")}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-label text-muted">Минимум</dt>
                    <dd className="tnum mt-1 text-2xl font-medium text-ink">
                      {formatRub(summary.min_price)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-label text-muted">Медиана</dt>
                    <dd className="tnum mt-1 text-2xl font-medium text-ink">
                      {formatRub(summary.median_price)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-label text-muted">Максимум</dt>
                    <dd className="tnum mt-1 text-2xl font-medium text-ink">
                      {formatRub(summary.max_price)}
                    </dd>
                  </div>
                </dl>
              </section>
            )}

            {!loading && result && (
              <div className="flex flex-wrap gap-2 text-xs">
                {result.query.corrected !== result.query.original && (
                  <span className="rounded-pill border border-rule bg-paper-2 px-3 py-1 text-ink-2">
                    исправлено: {result.query.original} → {result.query.corrected}
                  </span>
                )}
                {result.query.synonyms_used.length > 0 && (
                  <span className="rounded-pill border border-rule bg-paper-2 px-3 py-1 text-ink-2">
                    синонимы: {result.query.synonyms_used.join(", ")}
                  </span>
                )}
                <span className="rounded-pill border border-rule bg-paper-2 px-3 py-1 text-ink-2">
                  регион: {result.query.region_name}
                </span>
                <span className="tnum rounded-pill border border-rule bg-paper-2 px-3 py-1 text-ink-2">
                  {result.query.took_ms} ms
                </span>
              </div>
            )}

            <div className="grid gap-5 md:grid-cols-2">
              {fixedGroups.map((group) => (
                <SourceGroup
                  key={group.source}
                  group={group}
                  pending={loading && !presentSources.has(group.source)}
                />
              ))}
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-2 gap-y-1 px-5 py-5 text-xs text-muted">
          <span className="font-medium text-ink-2">Тендер-Поиск</span>
          <span aria-hidden="true">·</span>
          <span>агрегатор цен по маркетплейсам и Рунету</span>
          <span aria-hidden="true">·</span>
          <span className="tnum">2026</span>
        </div>
      </footer>
    </div>
  );
}
