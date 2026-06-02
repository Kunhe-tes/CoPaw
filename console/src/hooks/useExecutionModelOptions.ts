import { useCallback, useEffect, useMemo, useState } from "react";
import { providerApi } from "@/api/modules/provider";
import type {
  ActiveModelsInfo,
  ModelSlotConfig,
  ProviderInfo,
} from "@/api/types";

export const DEFAULT_EXECUTION_MODEL_KEY = "__DEFAULT__";

export interface ExecutionModelOption {
  key: string;
  providerId: string;
  providerName: string;
  model: string;
  modelName: string;
  label: string;
}

function isConfiguredProvider(provider: ProviderInfo): boolean {
  const hasModels =
    (provider.models?.length ?? 0) + (provider.extra_models?.length ?? 0) > 0;
  if (!hasModels) {
    return false;
  }
  if (provider.require_api_key === false) {
    return Boolean(provider.base_url);
  }
  if (provider.is_custom) {
    return Boolean(provider.base_url);
  }
  if (provider.require_api_key ?? true) {
    return Boolean(provider.api_key);
  }
  return true;
}

export function buildExecutionModelKey(
  modelSlot?: ModelSlotConfig | null,
): string {
  if (!modelSlot?.provider_id || !modelSlot?.model) {
    return DEFAULT_EXECUTION_MODEL_KEY;
  }
  return `${modelSlot.provider_id}::${modelSlot.model}`;
}

export function parseExecutionModelKey(
  value?: string,
): ModelSlotConfig | undefined {
  if (!value || value === DEFAULT_EXECUTION_MODEL_KEY) {
    return undefined;
  }
  const [provider_id, model] = value.split("::");
  if (!provider_id || !model) {
    return undefined;
  }
  return { provider_id, model };
}

export function buildExecutionModelOptions(
  providers: ProviderInfo[],
): ExecutionModelOption[] {
  return providers
    .filter(isConfiguredProvider)
    .flatMap((provider) =>
      [...(provider.models ?? []), ...(provider.extra_models ?? [])].map(
        (model) => ({
          key: buildExecutionModelKey({
            provider_id: provider.id,
            model: model.id,
          }),
          providerId: provider.id,
          providerName: provider.name,
          model: model.id,
          modelName: model.name || model.id,
          label: `${provider.name} / ${model.name || model.id}`,
        }),
      ),
    );
}

function fallbackModelLabel(modelSlot?: ModelSlotConfig | null): string {
  if (!modelSlot?.provider_id || !modelSlot?.model) {
    return "租户默认模型";
  }
  return `租户默认模型 (${modelSlot.provider_id} / ${modelSlot.model})`;
}

export function buildTenantDefaultModelLabel(
  activeModels: ActiveModelsInfo | null,
  options: ExecutionModelOption[],
): string {
  const matched = options.find(
    (option) =>
      option.providerId === activeModels?.active_llm?.provider_id &&
      option.model === activeModels?.active_llm?.model,
  );
  if (matched) {
    return `租户默认模型 (${matched.label})`;
  }
  return fallbackModelLabel(activeModels?.active_llm);
}

export function formatExecutionModelLabel(
  modelSlot: ModelSlotConfig | null | undefined,
  options: ExecutionModelOption[],
  tenantDefaultLabel: string,
): string {
  if (!modelSlot) {
    return tenantDefaultLabel;
  }
  const matched = options.find(
    (option) =>
      option.providerId === modelSlot.provider_id &&
      option.model === modelSlot.model,
  );
  return matched?.label || `${modelSlot.provider_id} / ${modelSlot.model}`;
}

export function useExecutionModelOptions(enabled = true) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [activeModels, setActiveModels] = useState<ActiveModelsInfo | null>(
    null,
  );
  const [loading, setLoading] = useState(false);

  const fetchOptions = useCallback(async () => {
    if (!enabled) {
      return;
    }
    setLoading(true);
    try {
      const [providerData, activeModelData] = await Promise.all([
        providerApi.listProviders(),
        providerApi.getActiveModels({ scope: "effective" }),
      ]);
      setProviders(Array.isArray(providerData) ? providerData : []);
      setActiveModels(activeModelData || null);
    } catch (error) {
      console.error("Failed to load execution model options", error);
      setProviders([]);
      setActiveModels(null);
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  const options = useMemo(
    () => buildExecutionModelOptions(providers),
    [providers],
  );
  const tenantDefaultLabel = useMemo(
    () => buildTenantDefaultModelLabel(activeModels, options),
    [activeModels, options],
  );

  return {
    loading,
    options,
    tenantDefaultLabel,
    refresh: fetchOptions,
  };
}
