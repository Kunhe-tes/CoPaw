import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "../api/request";
import { useProviderModelStore } from "./providerModelStore";
import { useIframeStore } from "./iframeStore";
import type { ProviderInfo } from "../api/types";

vi.mock("../api/request", () => ({
  request: vi.fn(),
}));

function provider(
  id: string,
  models: ProviderInfo["models"] = [],
): ProviderInfo {
  return {
    id,
    name: id,
    api_key_prefix: "",
    chat_model: "",
    models,
    extra_models: [],
    is_custom: false,
    is_local: false,
    support_model_discovery: false,
    support_connection_check: false,
    freeze_url: false,
    require_api_key: false,
    api_key: "",
    base_url: "http://localhost",
    generate_kwargs: {},
  };
}

describe("providerModelStore", () => {
  beforeEach(() => {
    vi.useRealTimers();
    useProviderModelStore.getState().reset();
    useIframeStore.setState({
      source: "source-a",
      space: "space-a",
      orgCode: "org-a",
      bbk: "bbk-a",
      userId: "user-a",
      authHeaders: [],
    });
    vi.clearAllMocks();
  });

  it("deduplicates concurrent provider and active model loads for the same runtime request identity", async () => {
    vi.mocked(request)
      .mockResolvedValueOnce([
        provider("openai", [
          {
            id: "gpt-4",
            name: "GPT-4",
            supports_multimodal: true,
            supports_image: true,
            supports_video: false,
          },
        ]),
      ])
      .mockResolvedValueOnce({
        active_llm: { provider_id: "openai", model: "gpt-4" },
      });

    const store = useProviderModelStore.getState();
    const [first, second] = await Promise.all([
      store.loadModelData(),
      store.loadModelData(),
    ]);

    expect(first.activeModels?.active_llm?.model).toBe("gpt-4");
    expect(second.providers[0]?.id).toBe("openai");
    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenCalledWith("/models");
    expect(request).toHaveBeenCalledWith("/models/active?scope=effective");
  });

  it("serves cached model data within the ttl and reloads after it expires", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000);
    vi.mocked(request)
      .mockResolvedValueOnce([provider("openai")])
      .mockResolvedValueOnce({
        active_llm: { provider_id: "openai", model: "gpt-4" },
      })
      .mockResolvedValueOnce([provider("qwen")])
      .mockResolvedValueOnce({
        active_llm: { provider_id: "qwen", model: "qwen-max" },
      });

    const store = useProviderModelStore.getState();
    await store.loadModelData();
    vi.setSystemTime(4_000);
    const cached = await store.loadModelData();
    vi.setSystemTime(7_000);
    const reloaded = await store.loadModelData();

    expect(cached.providers[0]?.id).toBe("openai");
    expect(reloaded.providers[0]?.id).toBe("qwen");
    expect(request).toHaveBeenCalledTimes(4);
  });

  it("shares provider loads across different active model params", async () => {
    vi.mocked(request)
      .mockImplementationOnce(async () => [provider("openai")])
      .mockImplementationOnce(async () => ({
        active_llm: { provider_id: "openai", model: "gpt-4" },
      }))
      .mockImplementationOnce(async () => ({
        active_llm: { provider_id: "openai", model: "gpt-4o" },
      }));

    const store = useProviderModelStore.getState();
    await Promise.all([
      store.loadModelData({ scope: "effective", agent_id: "agent-a" }),
      store.loadModelData({ scope: "effective", agent_id: "agent-b" }),
    ]);

    expect(request).toHaveBeenCalledTimes(3);
    expect(request).toHaveBeenCalledWith("/models");
    expect(request).toHaveBeenCalledWith(
      "/models/active?scope=effective&agent_id=agent-a",
    );
    expect(request).toHaveBeenCalledWith(
      "/models/active?scope=effective&agent_id=agent-b",
    );
  });
});
