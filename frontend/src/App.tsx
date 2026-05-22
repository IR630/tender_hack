import { FormEvent, useState } from "react";

import { DEFAULT_REGION_ID, loadStoredRegion, RegionSelector } from "./components/RegionSelector";
import { SourceGroup } from "./components/SourceGroup";
import type { SearchResponse } from "./types/search";

const SOURCE_ORDER = ["wildberries", "yandex_market", "ozon", "other"] as const;

export default function App() {
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState(loadStoredRegion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, region: region || DEFAULT_REGION_ID }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const payload = (await response.json()) as SearchResponse;
      setResult(payload);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Unknown error");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const orderedGroups = result
    ? SOURCE_ORDER.map((source) => result.groups.find((group) => group.source === source)).filter(
        (group): group is NonNullable<typeof group> => Boolean(group),
      )
    : [];

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

      {result && (
        <div className="space-y-4">
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
            <span className="rounded-full bg-slate-800 px-3 py-1">
              {result.query.took_ms} ms
            </span>
          </div>

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
