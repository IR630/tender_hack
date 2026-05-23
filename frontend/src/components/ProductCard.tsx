import { useEffect, useState } from "react";

import type { Product } from "../types/search";

interface ProductCardProps {
  product: Product;
}

function formatPrice(price: number): string {
  return `${Math.round(price / 100).toLocaleString("ru-RU")} ₽`;
}

function nextBasketUrl(url: string): string | null {
  const match = url.match(/basket-(\d+)\.wbbasket\.ru/);
  if (!match) {
    return null;
  }
  const host = Number.parseInt(match[1], 10);
  if (host >= 50) {
    return null;
  }
  return url.replace(/basket-\d+/, `basket-${String(host + 1).padStart(2, "0")}`);
}

export function ProductCard({ product }: ProductCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [imageSrc, setImageSrc] = useState(product.image_url);
  const hasDescription = product.description.trim().length > 0;

  useEffect(() => {
    setImageSrc(product.image_url);
  }, [product.image_url]);

  return (
    <li className="rounded-input border border-rule bg-paper p-3 transition-colors hover:border-rule-2">
      <div className="flex gap-3">
        {imageSrc ? (
          <img
            src={imageSrc}
            alt=""
            loading="lazy"
            className="h-16 w-16 shrink-0 rounded-input border border-rule bg-paper-3 object-cover"
            onError={() => {
              const fallback = nextBasketUrl(imageSrc);
              if (fallback) {
                setImageSrc(fallback);
              }
            }}
          />
        ) : (
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-input border border-rule bg-paper-3 text-xs text-muted">
            нет фото
          </div>
        )}

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug text-ink">{product.title}</p>
          <p className="tnum mt-1 text-base font-semibold text-ink">{formatPrice(product.price)}</p>

          {(product.rating !== null || product.reviews_count !== null) && (
            <p className="tnum mt-1 text-xs text-muted">
              {product.rating !== null && `★ ${product.rating}`}
              {product.reviews_count !== null && ` · ${product.reviews_count} отзывов`}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            {hasDescription && (
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="rounded-sm text-xs text-muted underline-offset-2 outline-none transition-colors hover:text-ink hover:underline focus-visible:ring-2 focus-visible:ring-focus/60"
              >
                {expanded ? "Скрыть описание" : "Показать описание"}
              </button>
            )}
            <a
              href={product.product_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-sm text-xs font-medium text-ink underline-offset-2 outline-none transition-colors hover:underline focus-visible:ring-2 focus-visible:ring-focus/60"
            >
              Открыть на маркетплейсе →
            </a>
          </div>
        </div>
      </div>

      {expanded && hasDescription && (
        <div className="mt-3 max-h-80 overflow-y-auto rounded-input border border-rule bg-paper-2 p-3 text-sm leading-relaxed text-ink-2 whitespace-pre-line">
          {product.description}
        </div>
      )}
    </li>
  );
}
