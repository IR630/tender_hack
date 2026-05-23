import { FormEvent, useEffect, useRef, useState } from "react";

import { DEFAULT_REGION_ID, loadStoredRegion, RegionSelector } from "./components/RegionSelector";
import { SearchLoader } from "./components/SearchLoader";
import { SourceGroup } from "./components/SourceGroup";
import type {
  SearchResponse,
  SearchTaskCreateResponse,
  SearchTaskStatusResponse,
} from "./types/search";
import { SEARCH_POLL_INTERVAL_MS } from "./types/search";

const SOURCE_ORDER = ["wildberries", "yandex_market", "ozon", "other"] as const;

function orderGroups(groups: SearchResponse["groups"]) {
  return SOURCE_ORDER.map((source) => groups.find((group) => group.source === source)).filter(
    (group): group is NonNullable<typeof group> => Boolean(group),
  );
}

export default function App() {
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState(loadStoredRegion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

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

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-4 py-10">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Tender Hack</p>
        <h1 className="text-3xl font-bold">Поиск цен по маркетплейсам и Рунету</h1>
        <p className="text-slate-400">
          Агрегатор цен с группировкой по источникам, исправлением опечаток и синонимами.
        </p>
      </header>

      <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <RegionSelector value={region} onChange={setRegion} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Например: айфон 15 про 256"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 outline-none ring-emerald-500 focus:ring-2"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-emerald-500 px-6 py-3 font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Ищем..." : "Найти"}
        </button>
      </form>

      {error && (
        <p className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-red-300">
          {error}
        </p>
      )}

      {loading && orderedGroups.length === 0 && <SearchLoader query={query} statusMessage={statusMessage} />}

      {(loading || result) && orderedGroups.length > 0 && (
        <div className="space-y-4">
          {loading && (
            <p className="text-sm text-slate-400">Частичные результаты (Ozon — до 35 с)…</p>
          )}
          {!loading && result && (
            <div className="flex flex-wrap gap-2 text-sm">
              {result.query.corrected !== result.query.original && (
                <span className="rounded-full bg-slate-800 px-3 py-1">
                  исправлено: {result.query.original} → {result.query.corrected}
                </span>
              )}
              {result.query.synonyms_used.length > 0 && (
                <span className="rounded-full bg-slate-800 px-3 py-1">
                  синонимы: {result.query.synonyms_used.join(", ")}
                </span>
              )}
              <span className="rounded-full bg-slate-800 px-3 py-1">
                регион: {result.query.region_name}
              </span>
              {!loading && (
                <span className="rounded-full bg-slate-800 px-3 py-1">
                  {result.query.took_ms} ms
                </span>
              )}
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {orderedGroups.map((group) => (
              <SourceGroup key={group.source} group={group} />
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
