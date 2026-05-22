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

export function SourceGroup({ group }: SourceGroupProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{group.display_name}</h2>
        <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-300">
          {group.count} предложений · от {formatPrice(group.min_price)}
        </span>
      </header>

      {group.products.length === 0 ? (
        <p className="text-sm text-slate-400">
          Пока нет данных — модуль источника в разработке.
        </p>
      ) : (
        <ul className="space-y-3">
          {group.products.slice(0, 10).map((product) => (
            <ProductCard key={`${product.source}-${product.product_url}`} product={product} />
          ))}
          {group.products.length > 10 && (
            <p className="text-sm text-slate-400">
              и ещё {group.products.length - 10} предложений
            </p>
          )}
        </ul>
      )}
    </section>
  );
}
