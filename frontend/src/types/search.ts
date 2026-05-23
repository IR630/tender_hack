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
  error?: string | null;
}

export interface SearchResponse {
  query: {
    original: string;
    corrected: string;
    region: string;
    region_name: string;
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

export interface SearchTaskCreateResponse {
  task_id: string;
}

export type SearchTaskStatus = "pending" | "running" | "completed" | "failed";

export interface SearchTaskStatusResponse {
  task_id: string;
  status: SearchTaskStatus;
  message?: string | null;
  error?: string | null;
  result?: SearchResponse | null;
  groups: SearchGroup[];
}

export const SEARCH_POLL_INTERVAL_MS = 3000;
