import { afterEach, describe, expect, it, vi } from "vitest";

describe("browser compatibility polyfills", () => {
  const originalArrayAt = (Array.prototype as { at?: unknown }).at;
  const originalStringAt = (String.prototype as { at?: unknown }).at;
  const originalStructuredClone = globalThis.structuredClone;
  const originalObjectHasOwn = (
    Object as ObjectConstructor & { hasOwn?: unknown }
  ).hasOwn;

  afterEach(() => {
    vi.resetModules();
    Object.defineProperty(Array.prototype, "at", {
      configurable: true,
      writable: true,
      value: originalArrayAt,
    });
    Object.defineProperty(String.prototype, "at", {
      configurable: true,
      writable: true,
      value: originalStringAt,
    });
    if (originalStructuredClone) {
      globalThis.structuredClone = originalStructuredClone;
    } else {
      delete (globalThis as typeof globalThis & { structuredClone?: unknown })
        .structuredClone;
    }
    if (originalObjectHasOwn) {
      (Object as ObjectConstructor & { hasOwn?: unknown }).hasOwn =
        originalObjectHasOwn;
    } else {
      delete (Object as ObjectConstructor & { hasOwn?: unknown }).hasOwn;
    }
  });

  it("installs missing at() methods without replacing native methods", async () => {
    const nativeArrayAt = (Array.prototype as { at?: unknown }).at;
    Object.defineProperty(Array.prototype, "at", {
      configurable: true,
      writable: true,
      value: undefined,
    });
    Object.defineProperty(String.prototype, "at", {
      configurable: true,
      writable: true,
      value: undefined,
    });

    await import("./browserCompat");

    expect(([1, 2, 3] as unknown as { at(index: number): number }).at(-1)).toBe(
      3,
    );
    expect(("abc" as unknown as { at(index: number): string }).at(-2)).toBe(
      "b",
    );

    Object.defineProperty(Array.prototype, "at", {
      configurable: true,
      writable: true,
      value: nativeArrayAt,
    });
    await import("./browserCompat");
    expect((Array.prototype as { at?: unknown }).at).toBe(nativeArrayAt);
  });

  it("installs structuredClone only when it is missing", async () => {
    vi.stubGlobal("structuredClone", undefined);

    await import("./browserCompat");

    const cloned = structuredClone({
      nested: { value: 1 },
      list: [1, 2, 3],
    });
    cloned.nested.value = 2;
    expect(cloned).toEqual({ nested: { value: 2 }, list: [1, 2, 3] });
  });

  it("installs Object.hasOwn only when it is missing", async () => {
    vi.stubGlobal("Object", Object);
    Object.defineProperty(Object, "hasOwn", {
      configurable: true,
      writable: true,
      value: undefined,
    });

    await import("./browserCompat");

    const hasOwn = (
      Object as ObjectConstructor & {
        hasOwn(object: object, property: PropertyKey): boolean;
      }
    ).hasOwn;
    expect(hasOwn({ value: 1 }, "value")).toBe(true);
    expect(hasOwn(Object.create({ inherited: 1 }), "inherited")).toBe(false);
  });
});
