import { useEffect, useState } from "react";

import { ProductCard } from "./ProductCard";
import type { SearchGroup } from "../types/search";

interface SourceGroupProps {
  group: SearchGroup;
  pending?: boolean;
}

function formatPrice(price: number | null): string {
  if (price === null) {
    return "—";
  }
  return `${Math.round(price / 100).toLocaleString("ru-RU")} ₽`;
}

const PAGE_SIZE = 10;

function productLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return "товар";
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return "товара";
  }
  return "товаров";
}

export function SourceGroup({ group, pending = false }: SourceGroupProps) {
  const totalCount = Math.max(group.count, group.products.length);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const shownCount = Math.min(visibleCount, group.products.length);
  const remainingCount = Math.max(0, totalCount - shownCount);
  const nextBatchSize = Math.min(PAGE_SIZE, remainingCount);
  const nextVisibleCount = Math.min(shownCount + nextBatchSize, totalCount);

  const firstProductUrl = group.products[0]?.product_url;
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [group.source, totalCount, firstProductUrl]);

  return (
    <section className="rounded-card border border-rule bg-paper-2 p-5">
      <header className="mb-4 flex items-baseline justify-between gap-3 border-b border-rule pb-3">
        <h2 className="text-base font-semibold tracking-display text-ink">{group.display_name}</h2>
        <span className="tnum shrink-0 text-sm text-muted">
          {pending ? (
            "ищем…"
          ) : (
            <>
              {group.count} · от <span className="text-ink-2">{formatPrice(group.min_price)}</span>
            </>
          )}
        </span>
      </header>

      {pending && group.products.length === 0 ? (
        <ul className="space-y-3" aria-hidden="true">
          {[0, 1].map((row) => (
            <li key={row} className="flex gap-3 rounded-input border border-rule bg-paper p-3">
              <div className="h-16 w-16 shrink-0 rounded-input bg-paper-3 motion-safe:animate-pulse" />
              <div className="flex-1 space-y-2 py-1.5">
                <div className="h-3 w-3/4 rounded bg-paper-3 motion-safe:animate-pulse" />
                <div className="h-3 w-2/5 rounded bg-paper-3 motion-safe:animate-pulse" />
                <div className="h-3 w-1/4 rounded bg-paper-3 motion-safe:animate-pulse" />
              </div>
            </li>
          ))}
        </ul>
      ) : group.products.length === 0 ? (
        <div className="text-sm">
          {group.status === "blocked_by_waf" ? (
            <p className="rounded-input border border-rule-2 bg-paper px-3 py-2 text-ink-2">
              {group.error ?? "Ozon: доступ временно ограничен защитой маркетплейса"}
            </p>
          ) : group.error ? (
            <p className="whitespace-pre-wrap rounded-input border border-rule-2 bg-paper px-3 py-2 text-ink-2">
              {group.error}
            </p>
          ) : group.source === "other" ? (
            <p className="text-muted">
              Нет результатов из сети. Повторите поиск — диагностика появится автоматически.
            </p>
          ) : (
            <p className="text-muted">Пока нет данных по этому источнику.</p>
          )}
        </div>
      ) : (
        <ul className="space-y-3">
          {group.products.slice(0, shownCount).map((product) => (
            <ProductCard key={`${product.source}-${product.product_url}`} product={product} />
          ))}
          {remainingCount > 0 && (
            <li>
              <button
                type="button"
                onClick={() =>
                  setVisibleCount((count) =>
                    Math.min(count + PAGE_SIZE, group.products.length, totalCount),
                  )
                }
                className="w-full rounded-input border border-rule bg-paper px-4 py-2 text-sm text-ink-2 outline-none transition-colors hover:border-ink-2 hover:bg-paper-3 active:bg-rule focus-visible:ring-2 focus-visible:ring-focus/60"
              >
                Показать ещё {nextBatchSize} {productLabel(nextBatchSize)} ·{" "}
                <span className="tnum">
                  {nextVisibleCount} из {totalCount}
                </span>
              </button>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
