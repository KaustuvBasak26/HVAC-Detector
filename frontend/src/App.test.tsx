import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  it("renders the main ingest heading", () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ jobs: [] }),
      } as Response),
    );

    render(<App />);
    expect(screen.getByText("Duct Analyzer")).toBeTruthy();
  });
});
