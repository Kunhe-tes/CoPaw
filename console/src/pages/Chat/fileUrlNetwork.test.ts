import { describe, expect, it } from "vitest";

import { resolveFileUrlNetworkFromHostname } from "./fileUrlNetwork";

describe("resolveFileUrlNetworkFromHostname", () => {
  it("uses business network when hostname contains paas.cmbchina.cn", () => {
    expect(resolveFileUrlNetworkFromHostname("paas.cmbchina.cn")).toBe(
      "business",
    );
    expect(resolveFileUrlNetworkFromHostname("copaw.paas.cmbchina.cn")).toBe(
      "business",
    );
  });

  it("uses office network for other hostnames", () => {
    expect(resolveFileUrlNetworkFromHostname("localhost")).toBe("office");
    expect(resolveFileUrlNetworkFromHostname("office.example.com")).toBe(
      "office",
    );
  });
});
