export type SourceType = "wildberries" | "ozon" | "yandex_market" | "other";

export interface Product {
  source: SourceType;
  source_domain: string;
  title: string;
  description: string;
  price: number;
  currency: string;
  image_url: string;
  product_url: string;
  characteristics: Record<string, string>;
  rating: number | null;
  reviews_count: number | null;
  relevance_score: number;
  confidence: number;
}

export interface SearchGroup {
  source: SourceType;
  display_name: string;
  count: number;
  min_price: number | null;
  domains: string[];
  products: Product[];
}

export interface SearchResponse {
  query: {
    original: string;
    corrected: string;
    synonyms_used: string[];
    took_ms: number;
  };
  summary: {
    total_found: number;
    min_price: number | null;
    median_price: number | null;
    max_price: number | null;
  };
  groups: SearchGroup[];
}
