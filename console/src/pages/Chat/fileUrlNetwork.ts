export type FileUrlNetwork = "office" | "business";

const BUSINESS_HOST_MARK = "paas.cmbchina.cn";

export function resolveFileUrlNetworkFromHostname(
  hostname: string,
): FileUrlNetwork {
  return hostname.includes(BUSINESS_HOST_MARK) ? "business" : "office";
}

export function resolveCurrentFileUrlNetwork(): FileUrlNetwork {
  return resolveFileUrlNetworkFromHostname(window.location.hostname);
}
