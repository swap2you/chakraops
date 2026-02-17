import { afterEach, expect } from "vitest";
import { cleanup } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";

expect.extend(matchers);

afterEach(() => cleanup());

// -----------------------------------------------------------------------------
// Browser API polyfills for JSDOM (matchMedia, ResizeObserver, etc.)
// -----------------------------------------------------------------------------

function noop(): void {}
function noopFalse(): boolean {
  return false;
}

if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    window.matchMedia = function matchMedia(_query: string): MediaQueryList {
      return {
        matches: false,
        media: _query,
        onchange: null,
        addListener: noop,
        removeListener: noop,
        addEventListener: noop,
        removeEventListener: noop,
        dispatchEvent: noopFalse,
      };
    };
  }
  if (!window.scrollTo) {
    window.scrollTo = noop;
  }
}

if (typeof globalThis !== "undefined") {
  if (typeof globalThis.ResizeObserver === "undefined") {
    globalThis.ResizeObserver = class ResizeObserver {
      observe = noop;
      unobserve = noop;
      disconnect = noop;
    };
  }
  if (typeof globalThis.IntersectionObserver === "undefined") {
    globalThis.IntersectionObserver = class IntersectionObserver {
      readonly root: Element | null = null;
      readonly rootMargin: string = "";
      readonly thresholds: readonly number[] = [];
      observe = noop;
      unobserve = noop;
      disconnect = noop;
      takeRecords = (): IntersectionObserverEntry[] => [];
    };
  }
}
