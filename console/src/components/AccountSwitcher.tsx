import { Dropdown, Avatar  } from "@agentscope-ai/design";
import { DownOutlined } from "@ant-design/icons";
import { Space } from "antd";
import type { MenuProps } from "antd";
import { useState } from "react";

interface Account {
  id: string;
  name: string;
  email: string;
  avatar?: string;
}

// Mock data - replace with actual data in production
const mockAccounts: Account[] = [
  { id: "1", name: "Alex Chen", email: "alex.chen@company.com", avatar: "AC" },
  { id: "2", name: "Sarah Miller", email: "sarah.m@company.com", avatar: "SM" },
  { id: "3", name: "James Wilson", email: "j.wilson@company.com", avatar: "JW" },
  { id: "4", name: "Emily Davis", email: "emily.d@company.com", avatar: "ED" },
];

interface AccountSwitcherProps {
  onSelect?: (userId: string) => void;
}

export default function AccountSwitcher({ onSelect }: AccountSwitcherProps) {
  const [selectedId, setSelectedId] = useState<string>(mockAccounts[0]?.id || "");

  const handleSelect = (id: string) => {
    setSelectedId(id);
    onSelect?.(id);
  };

  const selectedAccount = mockAccounts.find((acc) => acc.id === selectedId);

  const menuItems: MenuProps["items"] = mockAccounts.map((account) => ({
    key: account.id,
    label: (
      <div className="account-menu-item">
        <Space size={12}>
          <Avatar size={32} style={{ backgroundColor: "#615ced" }}>
            {account.avatar}
          </Avatar>
          <div className="account-info">
            <div className="account-name">{account.name}</div>
            <div className="account-email">{account.email}</div>
          </div>
        </Space>
      </div>
    ),
    onClick: () => handleSelect(account.id),
  }));

  return (
    <>
      <Dropdown menu={{ items: menuItems, selectedKeys: [selectedId] }} placement="bottomRight">
        <div className="account-switcher-trigger">
          <Space size={8}>
            <Avatar size={32} style={{ backgroundColor: "#615ced" }}>
              {selectedAccount?.avatar}
            </Avatar>
            <div className="trigger-info">
              <div className="trigger-name">{selectedAccount?.name}</div>
            </div>
            <DownOutlined className="trigger-arrow" />
          </Space>
        </div>
      </Dropdown>

      <style>{`
        .account-switcher-trigger {
          display: flex;
          align-items: center;
          padding: 6px 12px 6px 10px;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          border: 1px solid transparent;
        }

        .account-switcher-trigger:hover {
          background: rgba(97, 92, 237, 0.08);
          border-color: rgba(97, 92, 237, 0.2);
        }

        .trigger-info {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
        }

        .trigger-name {
          font-size: 14px;
          font-weight: 500;
          color: #1f2937;
          line-height: 1.2;
        }

        .trigger-arrow {
          font-size: 10px;
          color: #9ca3af;
          transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          margin-left: 4px;
        }

        .account-switcher-trigger:hover .trigger-arrow {
          transform: translateX(2px);
        }

        .account-menu-item {
          padding: 6px 0;
          transition: all 0.2s ease;
        }

        .account-info {
          display: flex;
          flex-direction: column;
        }

        .account-name {
          font-size: 14px;
          font-weight: 500;
          color: #1f2937;
          line-height: 1.3;
        }

        .account-email {
          font-size: 12px;
          color: #9ca3af;
          line-height: 1.3;
        }
      `}</style>
    </>
  );
}
