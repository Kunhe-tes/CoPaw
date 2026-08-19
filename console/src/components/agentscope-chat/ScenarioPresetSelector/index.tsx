import { Button, Spin } from "antd";
import { useEffect, useState } from "react";
import { scenarioPresetApi } from "@/api/modules/scenarioPreset";
import type {
  EffectiveScenarioPresetCatalog,
  ScenarioPresetCapability,
  ScenarioPresetScenario,
} from "@/api/types/scenarioPreset";

interface SelectedScenarioPreset {
  capability: ScenarioPresetCapability;
  scenario: ScenarioPresetScenario;
}

interface ScenarioPresetSelectorProps {
  disabled?: boolean;
  onSelect: (selection: SelectedScenarioPreset) => void;
}

/** Browse complete Source paths without resolving any market resource locally. */
export default function ScenarioPresetSelector({
  disabled = false,
  onSelect,
}: ScenarioPresetSelectorProps) {
  const [catalog, setCatalog] = useState<EffectiveScenarioPresetCatalog>();
  const [expandedCapabilityId, setExpandedCapabilityId] = useState<string>();

  useEffect(() => {
    let active = true;
    void scenarioPresetApi
      .getEffectiveCatalog()
      .then((result) => {
        if (!active || !result.domains.length) return;
        setCatalog(result);
        setExpandedCapabilityId(result.domains[0].capabilities[0]?.id);
      })
      .catch(() => {
        if (active) setCatalog({ domains: [] });
      });
    return () => {
      active = false;
    };
  }, []);

  if (!catalog) return <Spin size="small" aria-label="加载场景" />;
  if (!catalog.domains.length) return null;

  return (
    <div className="scenario-preset-selector" aria-label="能力与场景选择">
      {catalog.domains.flatMap((domain) =>
        domain.capabilities.map((capability) => (
          <div key={capability.id} className="scenario-preset-capability">
            <Button
              type={expandedCapabilityId === capability.id ? "link" : "text"}
              onClick={() => setExpandedCapabilityId(capability.id)}
              disabled={disabled}
              size="small"
            >
              {capability.name}
            </Button>
            {expandedCapabilityId === capability.id && (
              <div className="scenario-preset-scenarios">
                {capability.scenarios.map((scenario) => (
                  <Button
                    key={scenario.id}
                    type="text"
                    disabled={disabled}
                    onClick={() => onSelect({ capability, scenario })}
                    size="small"
                  >
                    {scenario.name}
                  </Button>
                ))}
              </div>
            )}
          </div>
        )),
      )}
    </div>
  );
}
