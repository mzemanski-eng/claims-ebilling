// Type declaration shim for react-simple-maps v3 (no @types package available).
// Provides minimal typings for the components used in us-spend-map.tsx.
declare module "react-simple-maps" {
  import * as React from "react";

  export interface ComposableMapProps {
    projection?: string;
    projectionConfig?: Record<string, unknown>;
    width?: number;
    height?: number;
    style?: React.CSSProperties;
    className?: string;
    children?: React.ReactNode;
  }
  export const ComposableMap: React.FC<ComposableMapProps>;

  export interface ZoomableGroupProps {
    center?: [number, number];
    zoom?: number;
    minZoom?: number;
    maxZoom?: number;
    translateExtent?: [[number, number], [number, number]];
    onMoveStart?: (position: { coordinates: [number, number]; zoom: number }) => void;
    onMove?: (position: { coordinates: [number, number]; zoom: number }) => void;
    onMoveEnd?: (position: { coordinates: [number, number]; zoom: number }) => void;
    children?: React.ReactNode;
  }
  export const ZoomableGroup: React.FC<ZoomableGroupProps>;

  export interface GeographiesProps {
    geography: string | Record<string, unknown>;
    children: (args: { geographies: Geography[] }) => React.ReactNode;
  }
  export const Geographies: React.FC<GeographiesProps>;

  export interface Geography {
    rsmKey: string;
    type: string;
    properties: Record<string, unknown>;
    geometry: Record<string, unknown>;
    id?: string | number;
  }

  export interface GeographyProps {
    geography: Geography;
    fill?: string;
    stroke?: string;
    strokeWidth?: number;
    style?: {
      default?: React.CSSProperties;
      hover?: React.CSSProperties;
      pressed?: React.CSSProperties;
    };
    onClick?: (geo: Geography) => void;
    onMouseEnter?: (geo: Geography) => void;
    onMouseLeave?: (geo: Geography) => void;
    className?: string;
    tabable?: boolean;
  }
  export const Geography: React.FC<GeographyProps>;
}
