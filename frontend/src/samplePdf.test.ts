import { describe, expect, it } from "vitest";

import { DEFAULT_SAMPLE } from "./samplePdf";

describe("samplePdf", () => {
  it("points at the bundled sample endpoint", () => {
    expect(DEFAULT_SAMPLE.downloadUrl).toBe("/api/samples/software-requirements-document");
    expect(DEFAULT_SAMPLE.name).toBe("Software Requirements Document.pdf");
  });
});
