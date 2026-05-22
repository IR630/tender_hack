import { useEffect, useState } from "react";

const STORAGE_KEY = "tender_hack_region";
export const DEFAULT_REGION_ID = "moscow";

export interface RegionOption {
  id: string;
  name: string;
}

interface RegionSelectorProps {
  value: string;
  onChange: (regionId: string) => void;
}

export function loadStoredRegion(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_REGION_ID;
  } catch {
    return DEFAULT_REGION_ID;
  }
}

export function storeRegion(regionId: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, regionId);
  } catch {
    // ignore private browsing / quota errors
  }
}

export function RegionSelector({ value, onChange }: RegionSelectorProps) {
  const [regions, setRegions] = useState<RegionOption[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function loadRegions() {
      try {
        const response = await fetch("/api/regions");
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as RegionOption[];
        if (!cancelled && payload.length > 0) {
          setRegions(payload);
        }
      } catch {
        // keep empty list; select still works with current value
      }
    }

    void loadRegions();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleChange(nextRegionId: string) {
    storeRegion(nextRegionId);
    onChange(nextRegionId);
  }

  const selectedName =
    regions.find((region) => region.id === value)?.name ??
    (value === DEFAULT_REGION_ID ? "Москва" : value);

  return (
    <label className="flex shrink-0 flex-col gap-1 sm:w-52">
      <span className="text-xs uppercase tracking-wide text-slate-400">Регион</span>
      <select
        value={value}
        onChange={(event) => handleChange(event.target.value)}
        aria-label={`Регион: ${selectedName}`}
        className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 outline-none ring-emerald-500 focus:ring-2"
      >
        {regions.length > 0 ? (
          regions.map((region) => (
            <option key={region.id} value={region.id}>
              {region.name}
            </option>
          ))
        ) : (
          <option value={DEFAULT_REGION_ID}>Москва</option>
        )}
      </select>
    </label>
  );
}
