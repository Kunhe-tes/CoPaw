import { useState } from "react";
import { Space } from "antd";
import { Input, Modal, Radio } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";

export interface ConflictItem {
  key: string;
  label: string;
  suggested_name: string;
}

interface InternalItem extends ConflictItem {
  new_name: string;
}

export type ConflictResolveMode = "rename" | "overwrite";

interface UseConflictRenameModalOptions {
  /** 是否显示覆盖选项，默认 false */
  showOverwriteOption?: boolean;
  /** 强制使用覆盖模式，不显示选择选项，默认 false */
  forceOverwrite?: boolean;
}

export function useConflictRenameModal(
  options?: UseConflictRenameModalOptions,
): {
  showConflictRenameModal: (
    items: ConflictItem[],
  ) => Promise<{ renameMap: Record<string, string> | null; mode: ConflictResolveMode } | null>;
  conflictRenameModal: React.ReactNode;
} {
  const { t } = useTranslation();
  const showOverwrite = options?.showOverwriteOption ?? false;
  const forceOverwrite = options?.forceOverwrite ?? false;
  const [items, setItems] = useState<InternalItem[]>([]);
  const [resolveMode, setResolveMode] = useState<ConflictResolveMode>(forceOverwrite ? "overwrite" : "rename");
  const [resolver, setResolver] = useState<
    ((result: { renameMap: Record<string, string> | null; mode: ConflictResolveMode } | null) => void) | null
  >(null);

  const showConflictRenameModal = (
    incoming: ConflictItem[],
  ): Promise<{ renameMap: Record<string, string> | null; mode: ConflictResolveMode } | null> =>
    new Promise((resolve) => {
      setItems(
        incoming.map((item) => ({ ...item, new_name: item.suggested_name })),
      );
      setResolveMode(forceOverwrite ? "overwrite" : "rename");
      setResolver(() => resolve);
    });

  const handleOk = () => {
    // 强制覆盖模式或选择覆盖模式时，返回 overwrite
    if (forceOverwrite || (showOverwrite && resolveMode === "overwrite")) {
      resolver?.({ renameMap: null, mode: "overwrite" });
    } else {
      const renameMap: Record<string, string> = {};
      for (const item of items) {
        if (item.new_name.trim()) {
          renameMap[item.key] = item.new_name.trim();
        }
      }
      resolver?.({ renameMap, mode: "rename" });
    }
    setItems([]);
    setResolver(null);
  };

  const handleCancel = () => {
    resolver?.(null);
    setItems([]);
    setResolver(null);
  };

  const conflictRenameModal = (
    <Modal
      open={items.length > 0}
      title={t("skillPool.multiConflictTitle")}
      onOk={handleOk}
      onCancel={handleCancel}
      zIndex={2100}
    >
      <p>{t("skillPool.multiConflictDesc")}</p>

      {/* 强制覆盖模式：只显示警告提示 */}
      {forceOverwrite && (
        <div style={{ padding: 12, backgroundColor: "#fffbe6", borderRadius: 6, border: "1px solid #ffe58f" }}>
          {t("skillPool.overwriteWarning", { count: items.length })}
        </div>
      )}

      {/* 覆盖选项：仅当 showOverwrite=true 且非强制覆盖时显示 */}
      {!forceOverwrite && showOverwrite && (
        <div style={{ marginBottom: 16 }}>
          <Radio.Group value={resolveMode} onChange={(e) => setResolveMode(e.target.value)}>
            <Space direction="vertical">
              <Radio value="rename">{t("skillPool.resolveModeRename")}</Radio>
              <Radio value="overwrite">{t("skillPool.resolveModeOverwrite")}</Radio>
            </Space>
          </Radio.Group>
        </div>
      )}

      {/* 重命名输入框：仅当非强制覆盖时显示 */}
      {!forceOverwrite && (!showOverwrite || resolveMode === "rename") && items.map((item, i) => (
        <div key={item.key} style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4 }}>
            {t("skillPool.renameEntry", { name: item.label })}
          </div>
          <Input
            value={item.new_name}
            onChange={(e) => {
              const next = [...items];
              next[i] = { ...next[i], new_name: e.target.value };
              setItems(next);
            }}
          />
        </div>
      ))}

      {/* 覆盖提示：仅当非强制覆盖且选择覆盖模式时显示 */}
      {!forceOverwrite && showOverwrite && resolveMode === "overwrite" && (
        <div style={{ padding: 12, backgroundColor: "#fffbe6", borderRadius: 6, border: "1px solid #ffe58f" }}>
          {t("skillPool.overwriteWarning", { count: items.length })}
        </div>
      )}
    </Modal>
  );

  return { showConflictRenameModal, conflictRenameModal };
}
