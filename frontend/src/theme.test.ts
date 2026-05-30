import { beforeEach, describe, expect, it, vi } from "vitest";

import { applyTheme, getStoredTheme, setTheme, toggleTheme } from "./theme";

function mockLocalStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
  });
}

describe("theme", () => {
  beforeEach(() => {
    mockLocalStorage();
    document.documentElement.removeAttribute("data-theme");
  });

  it("defaults to light theme", () => {
    expect(getStoredTheme()).toBe("light");
  });

  it("persists dark mode", () => {
    setTheme("dark");
    expect(getStoredTheme()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("toggles between light and dark", () => {
    setTheme("light");
    expect(toggleTheme("light")).toBe("dark");
    expect(toggleTheme("dark")).toBe("light");
  });

  it("updates theme-color meta tag", () => {
    const meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    document.head.appendChild(meta);
    applyTheme("dark");
    expect(meta.getAttribute("content")).toBe("#0c1222");
    applyTheme("light");
    expect(meta.getAttribute("content")).toBe("#2563eb");
    meta.remove();
  });
});
