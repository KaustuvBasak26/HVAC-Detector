export type SortKey = "segmentId" | "type" | "sizeText" | "lengthFt" | "confidence";
export type SortDir = "asc" | "desc";

export type SegmentRow = {
  segmentId: string;
  type: string;
  sizeText: string | null;
  lengthFt: number | null;
  confidence: number;
};

export function formatJobStep(step: string | null): string {
  if (!step) return "";
  if (/^Page \d+ of \d+:/.test(step)) return step;
  const s = step.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function compareSegments(a: SegmentRow, b: SegmentRow, key: SortKey, dir: SortDir): number {
  const mul = dir === "asc" ? 1 : -1;
  switch (key) {
    case "segmentId":
      return mul * a.segmentId.localeCompare(b.segmentId, undefined, { numeric: true });
    case "type":
      return mul * a.type.localeCompare(b.type);
    case "sizeText":
      return mul * (a.sizeText ?? "").localeCompare(b.sizeText ?? "");
    case "lengthFt": {
      const av = a.lengthFt ?? -1;
      const bv = b.lengthFt ?? -1;
      return mul * (av - bv);
    }
    case "confidence":
      return mul * (a.confidence - b.confidence);
    default:
      return 0;
  }
}

export function confidenceBarClass(c: number): string {
  if (c >= 0.7) return "conf-bar__fill conf-bar__fill--high";
  if (c >= 0.4) return "conf-bar__fill conf-bar__fill--mid";
  return "conf-bar__fill conf-bar__fill--low";
}
