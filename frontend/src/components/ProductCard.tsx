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
    <li className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex gap-3">
        {imageSrc ? (
          <img
            src={imageSrc}
            alt=""
            className="h-16 w-16 shrink-0 rounded-md bg-slate-800 object-cover"
            onError={() => {
              const fallback = nextBasketUrl(imageSrc);
              if (fallback) {
                setImageSrc(fallback);
              }
            }}
          />
        ) : (
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-md bg-slate-800 text-xs text-slate-500">
            нет фото
          </div>
        )}

        <div className="min-w-0 flex-1">
          <p className="font-medium leading-snug">{product.title}</p>
          <p className="mt-1 text-sm text-emerald-400">{formatPrice(product.price)}</p>

          {(product.rating !== null || product.reviews_count !== null) && (
            <p className="mt-1 text-xs text-slate-400">
              {product.rating !== null && `★ ${product.rating}`}
              {product.reviews_count !== null && ` · ${product.reviews_count} отзывов`}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-3">
            {hasDescription && (
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="text-xs text-violet-400 hover:text-violet-300"
              >
                {expanded ? "Скрыть описание" : "Показать описание"}
              </button>
            )}
            <a
              href={product.product_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-sky-400 hover:text-sky-300"
            >
              Открыть на маркетплейсе →
            </a>
          </div>
        </div>
      </div>

      {expanded && hasDescription && (
        <div className="mt-3 max-h-80 overflow-y-auto rounded-md border border-slate-800 bg-slate-900/80 p-3 text-sm leading-relaxed text-slate-300 whitespace-pre-line">
          {product.description}
        </div>
      )}
    </li>
  );
}
