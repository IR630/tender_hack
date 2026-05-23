import { useEffect, useState } from "react";

import { ProductCard } from "./ProductCard";
import type { SearchGroup } from "../types/search";

interface SourceGroupProps {
  group: SearchGroup;
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

export function SourceGroup({ group }: SourceGroupProps) {
  const totalCount = Math.max(group.count, group.products.length);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const shownCount = Math.min(visibleCount, group.products.length);
  const remainingCount = Math.max(0, totalCount - shownCount);
  const nextBatchSize = Math.min(PAGE_SIZE, remainingCount);
  const nextVisibleCount = Math.min(shownCount + nextBatchSize, totalCount);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [group.source, totalCount, group.products[0]?.product_url]);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{group.display_name}</h2>
        <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-300">
          {group.count} предложений · от {formatPrice(group.min_price)}
        </span>
      </header>

      {group.products.length === 0 ? (
        <div className="space-y-1 text-sm">
          {group.status === "blocked_by_waf" ? (
            <p className="rounded-md border border-orange-900/60 bg-orange-950/40 px-3 py-2 text-orange-200">
              {group.error ?? "Ozon: доступ временно ограничен защитой маркетплейса"}
            </p>
          ) : group.error ? (
            <p className="whitespace-pre-wrap rounded-md border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-sm text-amber-100">
              {group.error}
            </p>
          ) : group.source === "other" ? (
            <p className="text-slate-400">
              Нет результатов из сети. Повторите поиск — диагностика появится автоматически.
            </p>
          ) : (
            <p className="text-slate-400">Пока нет данных по этому источнику.</p>
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
                className="w-full rounded-lg border border-slate-700 bg-slate-900/80 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-slate-800"
              >
                Показать ещё {nextBatchSize} {productLabel(nextBatchSize)} · {nextVisibleCount}{" "}
                из {totalCount}
              </button>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
