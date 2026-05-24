import { useEffect, useMemo, useState } from "react";

import { ProductCard } from "./ProductCard";
import type { Product, SearchGroup } from "../types/search";

type SortDir = "none" | "asc" | "desc";

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

const INITIAL_VISIBLE = 5;
const EXPANSION_SIZE = 10;

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

function sortByPrice(products: Product[], dir: SortDir): Product[] {
  if (dir === "none") {
    return products;
  }
  const priced = products.filter((p) => p.price > 0);
  const unpriced = products.filter((p) => p.price <= 0);
  priced.sort((a, b) => (dir === "asc" ? a.price - b.price : b.price - a.price));
  return [...priced, ...unpriced];
}

export function SourceGroup({ group, pending = false }: SourceGroupProps) {
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE);
  const [sortDir, setSortDir] = useState<SortDir>("none");

  const firstProductUrl = group.products[0]?.product_url;
  useEffect(() => {
    setVisibleCount(INITIAL_VISIBLE);
    setSortDir("none");
  }, [group.source, firstProductUrl]);

  const products = useMemo(
    () => sortByPrice(group.products, sortDir),
    [group.products, sortDir],
  );
  const moreInFlight = group.status === "loading_more" && visibleCount >= products.length;
  const hasHidden = visibleCount < products.length;
  const isExpanded = visibleCount > INITIAL_VISIBLE;
  const fullyOpen = !hasHidden && !moreInFlight;
  const canSort = fullyOpen && products.length > 1;

  const handleShowMore = () =>
    setVisibleCount((c) => Math.min(c + EXPANSION_SIZE, products.length));
  const handleHide = () => setVisibleCount(INITIAL_VISIBLE);
  const handleToggleSort = () =>
    setSortDir((dir) => (dir === "none" ? "asc" : dir === "asc" ? "desc" : "none"));

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
        <>
          <ul className="space-y-3">
            {products.slice(0, visibleCount).map((product) => (
              <ProductCard key={`${product.source}-${product.product_url}`} product={product} />
            ))}
            {moreInFlight && (
              <li className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 animate-pulse">
                <p className="text-xs text-slate-400">
                  Синхронизация региональных цен и характеристик…
                </p>
              </li>
            )}
          </ul>

          {(hasHidden || moreInFlight || isExpanded || canSort) && (
            <div className="mt-4 flex flex-wrap gap-3">
              {(hasHidden || moreInFlight) && (
                <button
                  type="button"
                  onClick={handleShowMore}
                  disabled={moreInFlight}
                  className="rounded-input bg-accent px-4 py-2 text-sm font-medium text-accent-ink transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {moreInFlight
                    ? "Ищем ещё…"
                    : `Показать ещё ${Math.min(EXPANSION_SIZE, products.length - visibleCount)} ${productLabel(Math.min(EXPANSION_SIZE, products.length - visibleCount))}`}
                </button>
              )}
              {canSort && (
                <button
                  type="button"
                  onClick={handleToggleSort}
                  className="rounded-input border border-rule bg-paper px-4 py-2 text-sm font-medium text-ink-2 transition-colors hover:border-rule-2 hover:text-ink"
                >
                  {sortDir === "asc"
                    ? "Цена: по возрастанию ↑"
                    : sortDir === "desc"
                      ? "Цена: по убыванию ↓"
                      : "Сортировать по цене"}
                </button>
              )}
              {isExpanded && (
                <button
                  type="button"
                  onClick={handleHide}
                  className="rounded-input border border-rule bg-transparent px-4 py-2 text-sm font-medium text-muted transition-colors hover:border-rule-2 hover:text-ink"
                >
                  Скрыть
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}