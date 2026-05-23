import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

const STATUS_MESSAGES = [
  "Сканируем маркетплейсы…",
  "Исправляем опечатки в запросе…",
  "Подбираем синонимы…",
  "Учитываем регион доставки…",
  "Сравниваем цены…",
  "Собираем предложения…",
];

const SOURCES = [
  { id: "wildberries", label: "Wildberries" },
  { id: "yandex_market", label: "Яндекс Маркет" },
  { id: "ozon", label: "Ozon" },
  { id: "other", label: "Рунет" },
] as const;

const ORB = 40; // docked wheel diameter, px
const SCALE = 2.8; // centered scale → ~112px

type Phase = "centered" | "docked" | "exit";

interface SearchProgressProps {
  mainRef: RefObject<HTMLElement | null>;
  formRef: RefObject<HTMLFormElement | null>;
  loading: boolean;
  hasPartial: boolean;
  query: string;
  statusMessage?: string | null;
}

export function SearchProgress({
  mainRef,
  formRef,
  loading,
  hasPartial,
  query,
  statusMessage,
}: SearchProgressProps) {
  const [mounted, setMounted] = useState(loading);
  const [statusIndex, setStatusIndex] = useState(0);
  const [activeSource, setActiveSource] = useState(0);
  const slotRef = useRef<HTMLDivElement>(null);
  const [geom, setGeom] = useState({ left: 0, top: 0, dx: 0, dy: 0, statusRight: 0, statusTop: 0 });

  const phase: Phase = !loading ? "exit" : hasPartial ? "docked" : "centered";

  // keep mounted through the exit fade so the wheel doesn't vanish abruptly
  useEffect(() => {
    if (loading) {
      setMounted(true);
      return;
    }
    const timer = window.setTimeout(() => setMounted(false), 360);
    return () => window.clearTimeout(timer);
  }, [loading]);

  // rotating status + source highlight — only meaningful in the centered card
  useEffect(() => {
    if (!mounted) {
      return;
    }
    const statusTimer = window.setInterval(
      () => setStatusIndex((value) => (value + 1) % STATUS_MESSAGES.length),
      2200,
    );
    const sourceTimer = window.setInterval(
      () => setActiveSource((value) => (value + 1) % SOURCES.length),
      900,
    );
    return () => {
      window.clearInterval(statusTimer);
      window.clearInterval(sourceTimer);
    };
  }, [mounted]);

  useLayoutEffect(() => {
    if (!mounted) {
      return;
    }
    function measure() {
      const main = mainRef.current;
      const form = formRef.current;
      if (!main || !form) {
        return;
      }
      const mainRect = main.getBoundingClientRect();
      const formRect = form.getBoundingClientRect();
      const compact = window.innerWidth < 640;
      const inset = 16;
      const dockCenterX = mainRect.right - inset - ORB / 2;
      const dockCenterY = compact ? formRect.bottom + 28 : formRect.top + formRect.height / 2;
      const left = dockCenterX - mainRect.left - ORB / 2;
      const top = dockCenterY - mainRect.top - ORB / 2;

      setGeom((prev) => {
        let dx = prev.dx;
        let dy = prev.dy;
        const slot = slotRef.current;
        if (slot) {
          const slotRect = slot.getBoundingClientRect();
          dx = slotRect.left + slotRect.width / 2 - dockCenterX;
          dy = slotRect.top + slotRect.height / 2 - dockCenterY;
        }
        return {
          left,
          top,
          dx,
          dy,
          statusRight: main.clientWidth - left + 8,
          statusTop: top + ORB / 2 - 10,
        };
      });
    }

    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [mounted, phase, query, mainRef, formRef]);

  if (!mounted) {
    return null;
  }

  const orbTransform =
    phase === "centered"
      ? `translate(${geom.dx}px, ${geom.dy}px) scale(${SCALE})`
      : "translate(0px, 0px) scale(1)";

  const shortStatus = statusMessage ?? "Догружаем остальные источники… (Ozon — до 35 с)";

  return (
    <>
      {phase === "centered" && (
        <section
          className="mt-10 rounded-card border border-rule bg-paper-2 px-6 py-12"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="mx-auto flex max-w-md flex-col items-center gap-8">
            <div ref={slotRef} className="h-28 w-28" aria-hidden="true" />
            <div className="space-y-3 text-center">
              <p className="text-lg font-medium tracking-display text-ink">Ищем лучшие цены</p>
              {query.trim() && (
                <p className="mx-auto max-w-sm truncate rounded-pill border border-rule bg-paper px-4 py-1.5 text-sm text-ink-2">
                  «{query.trim()}»
                </p>
              )}
              <p
                key={statusMessage ?? statusIndex}
                className="search-loader__status min-h-[1.5rem] text-sm text-muted"
              >
                {statusMessage ?? STATUS_MESSAGES[statusIndex]}
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-2">
              {SOURCES.map((source, index) => (
                <span
                  key={source.id}
                  className={`rounded-pill border px-3 py-1 text-xs transition-colors duration-[220ms] ${
                    index === activeSource
                      ? "border-ink bg-accent text-accent-ink"
                      : "border-rule bg-paper text-muted"
                  }`}
                >
                  {source.label}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}

      <div
        className="progress-dock-status pointer-events-none absolute hidden text-right text-xs text-muted sm:block"
        style={{
          right: geom.statusRight,
          top: geom.statusTop,
          maxWidth: "14rem",
          opacity: phase === "docked" ? 1 : 0,
        }}
        aria-hidden="true"
      >
        {shortStatus}
      </div>

      <div
        className="progress-orb pointer-events-none absolute"
        style={{
          left: geom.left,
          top: geom.top,
          width: ORB,
          height: ORB,
          transform: orbTransform,
          opacity: phase === "exit" ? 0 : 1,
        }}
        role="status"
        aria-label="Идёт поиск"
      >
        <div className="absolute inset-0 rounded-pill border border-rule" />
        <div className="search-loader__sweep absolute inset-0 rounded-pill" />
        <div className="absolute inset-0 flex items-center justify-center">
          <svg
            viewBox="0 0 24 24"
            className="search-loader__pulse h-5 w-5 text-ink"
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
    </>
  );
}
