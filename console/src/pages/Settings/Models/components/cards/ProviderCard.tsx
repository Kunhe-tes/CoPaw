import type { ProviderInfo, ActiveModelsInfo } from "../../../../../api/types";
import { LocalProviderCard } from "./LocalProviderCard";
import { RemoteProviderCard } from "./RemoteProviderCard";

interface ProviderCardProps {
  provider: ProviderInfo;
  activeModels: ActiveModelsInfo | null;
  onSaved: () => void;
}

export function ProviderCard({
  provider,
  activeModels,
  onSaved,
}: ProviderCardProps) {
  if (provider.id === "copaw-local") {
    return <LocalProviderCard provider={provider} onSaved={onSaved} />;
  }

  return (
    <RemoteProviderCard
      provider={provider}
      activeModels={activeModels}
      onSaved={onSaved}
    />
  );
}
