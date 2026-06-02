/**
 * 浏览器兼容补丁只在原生能力缺失时安装，避免影响现代浏览器的原生实现。
 */

type CloneableRecord = Record<string, unknown>;

function isObjectLike(value: unknown): value is object {
  return typeof value === "object" && value !== null;
}

function cloneCompatValue<T>(
  value: T,
  seen = new WeakMap<object, unknown>(),
): T {
  if (!isObjectLike(value)) return value;

  if (seen.has(value)) {
    return seen.get(value) as T;
  }

  if (value instanceof Date) {
    return new Date(value.getTime()) as T;
  }

  if (value instanceof RegExp) {
    return new RegExp(value.source, value.flags) as T;
  }

  if (value instanceof Map) {
    const cloned = new Map();
    seen.set(value, cloned);
    value.forEach((mapValue, mapKey) => {
      cloned.set(
        cloneCompatValue(mapKey, seen),
        cloneCompatValue(mapValue, seen),
      );
    });
    return cloned as T;
  }

  if (value instanceof Set) {
    const cloned = new Set();
    seen.set(value, cloned);
    value.forEach((setValue) => {
      cloned.add(cloneCompatValue(setValue, seen));
    });
    return cloned as T;
  }

  if (ArrayBuffer.isView(value)) {
    const Ctor = value.constructor as new (source: ArrayBufferLike) => unknown;
    return new Ctor(value.buffer.slice(0)) as T;
  }

  if (value instanceof ArrayBuffer) {
    return value.slice(0) as T;
  }

  if (Array.isArray(value)) {
    const cloned: unknown[] = [];
    seen.set(value, cloned);
    value.forEach((item, index) => {
      cloned[index] = cloneCompatValue(item, seen);
    });
    return cloned as T;
  }

  const cloned: CloneableRecord = {};
  seen.set(value, cloned);
  Object.keys(value).forEach((key) => {
    cloned[key] = cloneCompatValue((value as CloneableRecord)[key], seen);
  });
  return cloned as T;
}

function at<T>(this: ArrayLike<T>, index: number): T | undefined {
  const length = this.length >>> 0;
  const relativeIndex = Math.trunc(index) || 0;
  const resolvedIndex =
    relativeIndex >= 0 ? relativeIndex : length + relativeIndex;
  if (resolvedIndex < 0 || resolvedIndex >= length) return undefined;
  return this[resolvedIndex];
}

if (typeof (Array.prototype as { at?: unknown }).at !== "function") {
  Object.defineProperty(Array.prototype, "at", {
    configurable: true,
    writable: true,
    value: at,
  });
}

if (typeof (String.prototype as { at?: unknown }).at !== "function") {
  Object.defineProperty(String.prototype, "at", {
    configurable: true,
    writable: true,
    value(index: number) {
      const char = at.call(this, index);
      return char === undefined ? undefined : String(char);
    },
  });
}

if (typeof globalThis.structuredClone !== "function") {
  Object.defineProperty(globalThis, "structuredClone", {
    configurable: true,
    writable: true,
    value: cloneCompatValue,
  });
}

const objectWithHasOwn = Object as ObjectConstructor & {
  hasOwn?: (object: object, property: PropertyKey) => boolean;
};

if (typeof objectWithHasOwn.hasOwn !== "function") {
  Object.defineProperty(Object, "hasOwn", {
    configurable: true,
    writable: true,
    value(object: object, property: PropertyKey): boolean {
      return Object.prototype.hasOwnProperty.call(Object(object), property);
    },
  });
}

export { cloneCompatValue };
