"use client";

/**
 * USSpendMap — interactive US choropleth showing spend by state.
 *
 * Uses react-simple-maps with US Atlas TopoJSON served from a CDN.
 * States are coloured by billed amount intensity; click to drill down.
 * Rendered client-side only (parent uses next/dynamic with ssr:false).
 */

import { useState } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  ZoomableGroup,
} from "react-simple-maps";
import type { SpendByState } from "@/lib/types";

// US states TopoJSON from public CDN — no API key required
const GEO_URL =
  "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";

// FIPS code → 2-letter state abbreviation
const FIPS_TO_STATE: Record<string, string> = {
  "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
  "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
  "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
  "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
  "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
  "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
  "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
  "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
  "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
  "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
  "56": "WY",
};

const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas",
  CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware",
  DC: "Washington D.C.", FL: "Florida", GA: "Georgia", HI: "Hawaii",
  ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas",
  KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah",
  VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia",
  WI: "Wisconsin", WY: "Wyoming",
};

function formatCurrency(val: string | number): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n) || n === 0) return "$0";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

/** Interpolate between two hex colours by t ∈ [0, 1]. */
function interpolateColor(t: number): string {
  // Light steel blue → deep blue
  const r = Math.round(219 - t * 177);
  const g = Math.round(234 - t * 148);
  const b = Math.round(254 - t * 100);
  return `rgb(${r},${g},${b})`;
}

interface Tooltip {
  state: string;
  name: string;
  billed: number;
  lines: number;
  x: number;
  y: number;
}

interface Props {
  data: SpendByState[];
  selectedState: string | null;
  onStateClick: (state: string) => void;
}

export default function USSpendMap({ data, selectedState, onStateClick }: Props) {
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  // Build lookup: state abbreviation → SpendByState
  const spendMap = new Map<string, SpendByState>(
    data.map((row) => [row.state, row])
  );

  const maxBilled = Math.max(
    ...data.map((r) => parseFloat(r.total_billed)),
    1
  );

  function getColor(stateAbbr: string): string {
    const row = spendMap.get(stateAbbr);
    if (!row) return "#F3F4F6"; // no data — light grey
    const billed = parseFloat(row.total_billed);
    const t = Math.min(billed / maxBilled, 1);
    return interpolateColor(t);
  }

  function getStrokeColor(stateAbbr: string): string {
    if (selectedState === stateAbbr) return "#1D4ED8";
    return "#FFFFFF";
  }

  function getStrokeWidth(stateAbbr: string): number {
    return selectedState === stateAbbr ? 2 : 0.5;
  }

  return (
    <div className="relative select-none">
      <ComposableMap
        projection="geoAlbersUsa"
        style={{ width: "100%", height: "auto" }}
        projectionConfig={{ scale: 900 }}
      >
        <ZoomableGroup>
          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const fips = String(geo.id).padStart(2, "0");
                const abbr = FIPS_TO_STATE[fips];
                if (!abbr) return null;

                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={getColor(abbr)}
                    stroke={getStrokeColor(abbr)}
                    strokeWidth={getStrokeWidth(abbr)}
                    style={{
                      default: { outline: "none", cursor: spendMap.has(abbr) ? "pointer" : "default" },
                      hover:   { outline: "none", fill: spendMap.has(abbr) ? "#93C5FD" : "#E5E7EB", cursor: spendMap.has(abbr) ? "pointer" : "default" },
                      pressed: { outline: "none" },
                    }}
                    onMouseEnter={(e) => {
                      const row = spendMap.get(abbr);
                      if (!row) return;
                      setTooltip({
                        state: abbr,
                        name: STATE_NAMES[abbr] ?? abbr,
                        billed: parseFloat(row.total_billed),
                        lines: row.line_count,
                        x: e.clientX,
                        y: e.clientY,
                      });
                    }}
                    onMouseMove={(e) => {
                      if (tooltip) {
                        setTooltip((prev) =>
                          prev ? { ...prev, x: e.clientX, y: e.clientY } : null
                        );
                      }
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    onClick={() => {
                      if (spendMap.has(abbr)) onStateClick(abbr);
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ZoomableGroup>
      </ComposableMap>

      {/* Floating tooltip */}
      {tooltip && (
        <div
          className="pointer-events-none fixed z-50 rounded-lg border bg-white px-3 py-2 shadow-xl text-xs"
          style={{ left: tooltip.x + 12, top: tooltip.y - 40 }}
        >
          <p className="font-bold text-gray-900">
            {tooltip.name} ({tooltip.state})
          </p>
          <p className="text-gray-600">
            Billed: <span className="font-semibold text-blue-700">{formatCurrency(tooltip.billed)}</span>
          </p>
          <p className="text-gray-400">{tooltip.lines} service line{tooltip.lines !== 1 ? "s" : ""}</p>
          <p className="mt-1 text-blue-500 text-xs">Click to filter ZIPs ↓</p>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-2 mt-2 justify-end pr-2">
        <span className="text-xs text-gray-400">Less</span>
        <div
          className="h-3 w-24 rounded-full"
          style={{
            background: "linear-gradient(to right, rgb(219,234,254), rgb(42,86,154))",
          }}
        />
        <span className="text-xs text-gray-400">More spend</span>
        <span className="ml-3 inline-flex items-center gap-1 text-xs text-gray-400">
          <span className="inline-block h-3 w-3 rounded-sm bg-gray-200 border border-gray-300" />
          No data
        </span>
      </div>
    </div>
  );
}
