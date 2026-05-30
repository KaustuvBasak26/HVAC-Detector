import { describe, expect, it } from "vitest";

import {
  compareSegments,
  confidenceBarClass,
  formatJobStep,
  type SegmentRow,
} from "./jobUtils";

const a: SegmentRow = {
  segmentId: "2",
  type: "supply",
  sizeText: "12x8",
  lengthFt: 10,
  confidence: 0.8,
};

const b: SegmentRow = {
  segmentId: "10",
  type: "return",
  sizeText: "8x8",
  lengthFt: 5,
  confidence: 0.5,
};

describe("formatJobStep", () => {
  it("returns empty for nullish", () => {
    expect(formatJobStep(null)).toBe("");
  });

  it("preserves page progress lines", () => {
    expect(formatJobStep("Page 2 of 5: rendering")).toBe("Page 2 of 5: rendering");
  });

  it("title-cases underscored steps", () => {
    expect(formatJobStep("queued")).toBe("Queued");
    expect(formatJobStep("export_segments")).toBe("Export segments");
  });
});

describe("compareSegments", () => {
  it("sorts segmentId numerically when ascending", () => {
    expect(compareSegments(a, b, "segmentId", "asc")).toBeLessThan(0);
    expect(compareSegments(b, a, "segmentId", "asc")).toBeGreaterThan(0);
  });

  it("reverses lengthFt when descending", () => {
    expect(compareSegments(a, b, "lengthFt", "desc")).toBeLessThan(0);
  });
});

describe("confidenceBarClass", () => {
  it("maps thresholds to CSS classes", () => {
    expect(confidenceBarClass(0.9)).toContain("high");
    expect(confidenceBarClass(0.5)).toContain("mid");
    expect(confidenceBarClass(0.2)).toContain("low");
  });
});
