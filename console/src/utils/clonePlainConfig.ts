/**
 * Source 配置是 JSON 兼容对象；优先使用原生 structuredClone，缺失时使用本地深拷贝。
 */
import { cloneCompatValue } from "./browserCompat";

export function clonePlainConfig<T>(config: T): T {
  if (typeof globalThis.structuredClone === "function") {
    return globalThis.structuredClone(config);
  }
  return cloneCompatValue(config);
}
