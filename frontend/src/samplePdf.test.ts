import { describe, expect, it } from "vitest";

import { DEFAULT_SAMPLE } from "./samplePdf";

describe("samplePdf", () => {
  it("points at the bundled testset2 sample endpoint", () => {
    expect(DEFAULT_SAMPLE.downloadUrl).toBe("/api/samples/testset2");
    expect(DEFAULT_SAMPLE.name).toBe("testset2.pdf");
  });
});
