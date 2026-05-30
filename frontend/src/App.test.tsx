import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  it("renders the main ingest heading", () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            maxUploadSizeMb: 10,
            demoMode: false,
            lowMemoryMode: false,
            samples: [],
          }),
      } as Response),
    );

    render(<App />);
    expect(screen.getByText("HVAC Duct Analyzer")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: /HVAC duct detection/i })).toBeTruthy();
  });
});
