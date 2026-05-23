import { useEffect, useState } from "react";

const SOURCES = [
  { id: "wildberries", label: "Wildberries", short: "WB", color: "#cb11ab", ring: "ring-fuchsia-500/60" },
  { id: "ozon", label: "Ozon", short: "OZ", color: "#005bff", ring: "ring-sky-500/60" },
  { id: "yandex_market", label: "Яндекс Маркет", short: "YM", color: "#ffcc00", ring: "ring-amber-400/60" },
  { id: "other", label: "Рунет", short: "RU", color: "#34d399", ring: "ring-emerald-400/60" },
] as const;

const STATUS_MESSAGES = [
  "Сканируем маркетплейсы…",
  "Исправляем опечатки в запросе…",
  "Подбираем синонимы…",
  "Учитываем регион доставки…",
  "Сравниваем цены…",
  "Собираем предложения…",
];

interface SearchLoaderProps {
  query: string;
  statusMessage?: string | null;
}

export function SearchLoader({ query, statusMessage }: SearchLoaderProps) {
  const [activeSource, setActiveSource] = useState(0);
  const [statusIndex, setStatusIndex] = useState(0);

  useEffect(() => {
    const sourceTimer = window.setInterval(() => {
      setActiveSource((value) => (value + 1) % SOURCES.length);
    }, 900);

    const statusTimer = window.setInterval(() => {
      setStatusIndex((value) => (value + 1) % STATUS_MESSAGES.length);
    }, 2200);

    return () => {
      window.clearInterval(sourceTimer);
      window.clearInterval(statusTimer);
    };
  }, []);

  const trimmedQuery = query.trim();

  return (
    <section
      className="search-loader relative overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/70 px-6 py-10"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="search-loader__grid pointer-events-none absolute inset-0 opacity-30" />
      <div className="search-loader__glow pointer-events-none absolute -left-20 top-1/2 h-56 w-56 -translate-y-1/2 rounded-full bg-emerald-500/10 blur-3xl" />
      <div className="search-loader__glow pointer-events-none absolute -right-16 bottom-0 h-48 w-48 rounded-full bg-violet-500/10 blur-3xl" />

      <div className="relative mx-auto flex max-w-lg flex-col items-center gap-8">
        <div className="relative h-44 w-44">
          <div className="search-loader__ring search-loader__ring--outer absolute inset-0 rounded-full border border-slate-700/60" />
          <div className="search-loader__ring search-loader__ring--middle absolute inset-4 rounded-full border border-slate-700/40" />
          <div className="search-loader__ring search-loader__ring--inner absolute inset-8 rounded-full border border-emerald-500/20" />

          <div className="search-loader__sweep absolute inset-0 rounded-full" />

          {SOURCES.map((source, index) => {
            const angle = (index / SOURCES.length) * 360 - 90;
            const radius = 78;
            const x = Math.cos((angle * Math.PI) / 180) * radius;
            const y = Math.sin((angle * Math.PI) / 180) * radius;
            const isActive = index === activeSource;

            return (
              <div
                key={source.id}
                className={`search-loader__node absolute left-1/2 top-1/2 flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border text-xs font-bold transition-all duration-500 ${
                  isActive
                    ? `scale-110 border-transparent bg-slate-900 ring-2 ${source.ring} shadow-lg`
                    : "scale-90 border-slate-700/80 bg-slate-950/80 text-slate-500"
                }`}
                style={{
                  transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`,
                  color: isActive ? source.color : undefined,
                  boxShadow: isActive ? `0 0 24px ${source.color}44` : undefined,
                }}
              >
                {source.short}
              </div>
            );
          })}

          <div className="absolute left-1/2 top-1/2 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-emerald-500/30 bg-slate-950/90 shadow-[0_0_40px_rgba(16,185,129,0.15)]">
            <svg
              viewBox="0 0 24 24"
              className="search-loader__pulse h-8 w-8 text-emerald-400"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
            </svg>
          </div>
        </div>

        <div className="space-y-3 text-center">
          <p className="text-lg font-semibold tracking-tight text-slate-100">
            Ищем лучшие цены
          </p>

          {trimmedQuery && (
            <p className="mx-auto max-w-sm truncate rounded-full border border-slate-800 bg-slate-950/70 px-4 py-1.5 text-sm text-emerald-300/90">
              «{trimmedQuery}»
            </p>
          )}

          <p
            key={statusMessage ?? statusIndex}
            className="search-loader__status min-h-[1.5rem] text-sm text-slate-400"
          >
            {statusMessage ?? STATUS_MESSAGES[statusIndex]}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2">
          {SOURCES.map((source, index) => (
            <span
              key={source.id}
              className={`rounded-full px-3 py-1 text-xs transition-all duration-500 ${
                index === activeSource
                  ? "bg-slate-800 text-slate-100"
                  : "bg-slate-950/50 text-slate-500"
              }`}
              style={index === activeSource ? { color: source.color } : undefined}
            >
              {source.label}
            </span>
          ))}
        </div>

        <div className="flex gap-1.5" aria-hidden="true">
          {[0, 1, 2].map((dot) => (
            <span
              key={dot}
              className="search-loader__dot h-1.5 w-1.5 rounded-full bg-emerald-400/80"
              style={{ animationDelay: `${dot * 0.18}s` }}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
