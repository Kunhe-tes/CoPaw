import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Button, Input } from "@agentscope-ai/design";
import { Collapse, Radio, Select, Spin } from "antd";
import { CheckOutlined, UserOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { BBK_ID_MAP, BBK_ID_TO_NAME_MAP } from "@/constants/bbk";
import {
  fetchTenantsBySource,
  type TenantSourceInfo,
} from "@/api/modules/userInfo";

interface TenantTargetPickerProps {
  tenantIds: string[];
  selectedTenantIds: string[];
  onChange: (tenantIds: string[]) => void;
  hint?: ReactNode;
  sourceId?: string;
}

function mergeTenantIds(
  discoveredTenantIds: string[],
  manualTenantIds: string[],
): string[] {
  return Array.from(new Set([...discoveredTenantIds, ...manualTenantIds]));
}

function haveSameTenantIds(left: string[], right: string[]): boolean {
  const leftTenantIds = Array.from(new Set(left));
  const rightTenantIds = Array.from(new Set(right));

  if (leftTenantIds.length !== rightTenantIds.length) {
    return false;
  }

  const rightSet = new Set(rightTenantIds);
  return leftTenantIds.every((tenantId) => rightSet.has(tenantId));
}

export function parseManualTenantIds(input: string): string[] {
  return Array.from(
    new Set(
      input
        .split(/[\s,]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

export function TenantTargetPicker({
  tenantIds,
  selectedTenantIds,
  onChange,
  hint,
  sourceId,
}: TenantTargetPickerProps) {
  const { t } = useTranslation();
  const [loadingTenantInfo, setLoadingTenantInfo] = useState(false);
  const [tenantOptions, setTenantOptions] = useState<TenantSourceInfo[]>([]);
  const [targetMode, setTargetMode] = useState<"bbk_id" | "user_id">(
    sourceId ? "bbk_id" : "user_id",
  );
  const [selectedBbkIds, setSelectedBbkIds] = useState<string[]>([]);
  const [selectedDiscoveredTenantIds, setSelectedDiscoveredTenantIds] =
    useState<string[]>([]);
  const [manualTenantIdsText, setManualTenantIdsText] = useState("");
  const enhancedMode = Boolean(sourceId);

  useEffect(() => {
    if (!sourceId) {
      setTenantOptions([]);
      setTargetMode("user_id");
      return;
    }
    setLoadingTenantInfo(true);
    setTargetMode("bbk_id");
    setSelectedBbkIds([]);
    setSelectedDiscoveredTenantIds([]);
    setManualTenantIdsText("");
    fetchTenantsBySource(sourceId)
      .then((items) => setTenantOptions(items))
      .catch(console.error)
      .finally(() => setLoadingTenantInfo(false));
  }, [sourceId]);

  const manualTenantIds = useMemo(
    () => parseManualTenantIds(manualTenantIdsText),
    [manualTenantIdsText],
  );

  const availableTenantIds = useMemo(() => {
    if (tenantIds.length > 0) {
      return tenantIds;
    }
    return tenantOptions.map((item) => item.tenant_id);
  }, [tenantIds, tenantOptions]);

  const tenantLookup = useMemo(() => {
    return new Map(tenantOptions.map((item) => [item.tenant_id, item]));
  }, [tenantOptions]);

  const filteredTenantIds = useMemo(() => {
    if (!enhancedMode || targetMode !== "bbk_id") {
      return availableTenantIds;
    }
    if (selectedBbkIds.length === 0) {
      return [];
    }
    return availableTenantIds.filter((tenantId) => {
      const tenant = tenantLookup.get(tenantId);
      return selectedBbkIds.includes(tenant?.bbk_id || "");
    });
  }, [
    availableTenantIds,
    enhancedMode,
    selectedBbkIds,
    targetMode,
    tenantLookup,
  ]);

  const manualTenantIdsInList = useMemo(() => {
    return manualTenantIds.filter((tenantId) =>
      availableTenantIds.includes(tenantId),
    );
  }, [availableTenantIds, manualTenantIds]);

  const manualTenantIdsOutsideList = useMemo(() => {
    return manualTenantIds.filter(
      (tenantId) => !availableTenantIds.includes(tenantId),
    );
  }, [availableTenantIds, manualTenantIds]);

  const mergedTenantIds = useMemo(() => {
    if (enhancedMode && targetMode === "bbk_id") {
      return filteredTenantIds;
    }
    return mergeTenantIds(selectedDiscoveredTenantIds, [
      ...manualTenantIdsInList,
      ...manualTenantIdsOutsideList,
    ]);
  }, [
    enhancedMode,
    filteredTenantIds,
    manualTenantIdsInList,
    manualTenantIdsOutsideList,
    selectedDiscoveredTenantIds,
    targetMode,
  ]);

  const groupedTenants = useMemo(() => {
    if (
      !enhancedMode ||
      targetMode !== "bbk_id" ||
      selectedBbkIds.length === 0
    ) {
      return [];
    }
    return selectedBbkIds
      .map((bbkId) => {
        const users = availableTenantIds
          .map((tenantId) => tenantLookup.get(tenantId))
          .filter(
            (tenant): tenant is TenantSourceInfo =>
              Boolean(tenant) && tenant?.bbk_id === bbkId,
          );
        return {
          bbkId,
          bbkName: BBK_ID_TO_NAME_MAP[bbkId] || bbkId,
          users,
        };
      })
      .filter((group) => group.users.length > 0);
  }, [
    availableTenantIds,
    enhancedMode,
    selectedBbkIds,
    targetMode,
    tenantLookup,
  ]);

  useEffect(() => {
    const discovered = selectedTenantIds.filter((tenantId) =>
      availableTenantIds.includes(tenantId),
    );
    const manual = selectedTenantIds.filter(
      (tenantId) => !availableTenantIds.includes(tenantId),
    );
    setSelectedDiscoveredTenantIds((current) =>
      haveSameTenantIds(current, discovered) ? current : discovered,
    );
    setManualTenantIdsText((current) => {
      const nextManualTenantIdsText = manual.join("\n");
      return current === nextManualTenantIdsText
        ? current
        : nextManualTenantIdsText;
    });
  }, [availableTenantIds, selectedTenantIds]);

  useEffect(() => {
    if (haveSameTenantIds(selectedTenantIds, mergedTenantIds)) {
      return;
    }
    onChange(mergedTenantIds);
  }, [mergedTenantIds, onChange, selectedTenantIds]);

  const handleModeChange = (mode: "bbk_id" | "user_id") => {
    setTargetMode(mode);
    setSelectedBbkIds([]);
    setSelectedDiscoveredTenantIds([]);
  };

  const renderTenantName = (tenantId: string) => {
    const tenant = tenantLookup.get(tenantId);
    return tenant?.tenant_name
      ? `${tenant.tenant_name} (${tenantId})`
      : tenantId;
  };

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {enhancedMode ? (
        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontWeight: 500 }}>分发目标</div>
          <Radio.Group
            value={targetMode}
            onChange={(event) => handleModeChange(event.target.value)}
          >
            <Radio value="bbk_id">按机构</Radio>
            <Radio value="user_id">按用户</Radio>
          </Radio.Group>
        </div>
      ) : null}

      {loadingTenantInfo ? (
        <Spin size="small" style={{ marginLeft: 16 }} />
      ) : null}

      {enhancedMode && targetMode === "bbk_id" ? (
        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontWeight: 500 }}>选择机构</div>
          <Select
            mode="multiple"
            placeholder="选择机构"
            value={selectedBbkIds}
            onChange={setSelectedBbkIds}
            options={BBK_ID_MAP}
            style={{ width: "100%" }}
          />
          <div style={{ color: "#666", fontSize: 12 }}>
            已选择 {selectedBbkIds.length} 个机构，涉及{" "}
            {filteredTenantIds.length} 个用户
          </div>
          {groupedTenants.length > 0 ? (
            <Collapse
              size="small"
              items={groupedTenants.map((group) => ({
                key: group.bbkId,
                label: (
                  <span style={{ fontSize: 13 }}>
                    <UserOutlined
                      style={{ marginRight: 6, color: "#1677ff" }}
                    />
                    {group.bbkName}
                    <span style={{ color: "#999", marginLeft: 8 }}>
                      {group.users.length} 人
                    </span>
                  </span>
                ),
                children: (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "repeat(auto-fit, minmax(130px, 1fr))",
                      gap: 4,
                    }}
                  >
                    {group.users.map((user) => (
                      <div
                        key={user.tenant_id}
                        style={{
                          fontSize: 12,
                          color: "#333",
                          padding: "2px 0",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={renderTenantName(user.tenant_id)}
                      >
                        {renderTenantName(user.tenant_id)}
                      </div>
                    ))}
                  </div>
                ),
              }))}
            />
          ) : null}
        </div>
      ) : null}

      {!enhancedMode || targetMode === "user_id" ? (
        <>
          <div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div style={{ fontWeight: 500 }}>
                {t("skillPool.selectWorkspaces")}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <Button
                  size="small"
                  onClick={() =>
                    setSelectedDiscoveredTenantIds(
                      Array.from(new Set(filteredTenantIds)),
                    )
                  }
                >
                  {t("skillPool.allWorkspaces")}
                </Button>
                <Button
                  size="small"
                  onClick={() => setSelectedDiscoveredTenantIds([])}
                >
                  {t("skills.clearSelection")}
                </Button>
              </div>
            </div>
            {hint ? (
              <div style={{ marginTop: 8, color: "#666", fontSize: 12 }}>
                {hint}
              </div>
            ) : null}
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              gap: 8,
              maxHeight: enhancedMode ? 240 : undefined,
              overflowY: enhancedMode ? "auto" : undefined,
            }}
          >
            {filteredTenantIds.map((tenantId) => {
              const selected =
                manualTenantIdsInList.includes(tenantId) ||
                selectedDiscoveredTenantIds.includes(tenantId);
              return (
                <button
                  key={tenantId}
                  type="button"
                  onClick={() =>
                    setSelectedDiscoveredTenantIds(
                      selected
                        ? selectedDiscoveredTenantIds.filter(
                            (id) => id !== tenantId,
                          )
                        : [...selectedDiscoveredTenantIds, tenantId],
                    )
                  }
                  style={{
                    cursor: "pointer",
                    borderRadius: 8,
                    border: selected
                      ? "1px solid #1677ff"
                      : "1px solid #d9d9d9",
                    background: selected ? "#eff6ff" : "#fff",
                    padding: "12px 14px",
                    textAlign: "left",
                    position: "relative",
                    fontSize: 12,
                  }}
                >
                  {selected ? (
                    <span style={{ position: "absolute", right: 10, top: 8 }}>
                      <CheckOutlined />
                    </span>
                  ) : null}
                  <span>{renderTenantName(tenantId)}</span>
                </button>
              );
            })}
          </div>

          <div>
            <div style={{ fontWeight: 500 }}>
              {t("skillPool.manualTenantIds")}
            </div>
            <div
              style={{
                marginTop: 8,
                marginBottom: 8,
                color: "#666",
                fontSize: 12,
              }}
            >
              {t("skillPool.manualTenantHint")}
            </div>
            <Input.TextArea
              rows={enhancedMode ? 3 : 4}
              value={manualTenantIdsText}
              onChange={(event) => setManualTenantIdsText(event.target.value)}
              placeholder={t("skillPool.manualTenantPlaceholder")}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}

export default TenantTargetPicker;
