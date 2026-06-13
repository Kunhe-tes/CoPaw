import type { MySkill } from "../../api/modules/mySkills";
import type { TenantSourceInfo } from "../../api/modules/userInfo";

export interface MarketSkillLookupSource {
  item_id: string;
  name: string;
  skill_name?: string | null;
  version?: string | null;
}

export interface SkillOwnerRow {
  tenant_id: string;
  tenant_name: string | null;
  bbk_id: string | null;
  skill_name: string;
  market_version: string | null;
  installed_version: string | null;
  received_version: string | null;
  enabled: boolean;
  has_update: boolean;
  match_source: "name_match";
}

interface BuildSkillOwnerRowsInput {
  marketSkill: MarketSkillLookupSource;
  tenants: TenantSourceInfo[];
  skillsByTenant: Record<string, MySkill[]>;
}

export function resolveMarketSkillName(
  marketSkill: MarketSkillLookupSource,
): string {
  return String(marketSkill.skill_name || marketSkill.name || "").trim();
}

function normalizeSkillName(value: string | null | undefined): string {
  return String(value || "").trim();
}

function resolveInstalledVersion(skill: MySkill): string | null {
  return skill.received_version || skill.version || null;
}

function needsUpdate(
  marketVersion: string | null,
  installedVersion: string | null,
  skill: MySkill,
): boolean {
  if (skill.has_update) {
    return true;
  }
  return Boolean(
    marketVersion &&
      installedVersion &&
      normalizeSkillName(marketVersion) !== normalizeSkillName(installedVersion),
  );
}

export function buildSkillOwnerRows({
  marketSkill,
  tenants,
  skillsByTenant,
}: BuildSkillOwnerRowsInput): SkillOwnerRow[] {
  const marketSkillName = resolveMarketSkillName(marketSkill);
  if (!marketSkillName) {
    return [];
  }
  const marketVersion = marketSkill.version || null;

  return tenants.flatMap((tenant) => {
    const matched = (skillsByTenant[tenant.tenant_id] || []).find(
      (skill) => normalizeSkillName(skill.skill_name) === marketSkillName,
    );
    if (!matched) {
      return [];
    }
    const installedVersion = resolveInstalledVersion(matched);
    return [
      {
        tenant_id: tenant.tenant_id,
        tenant_name: tenant.tenant_name,
        bbk_id: tenant.bbk_id,
        skill_name: matched.skill_name,
        market_version: marketVersion,
        installed_version: installedVersion,
        received_version: matched.received_version,
        enabled: matched.enabled,
        has_update: needsUpdate(marketVersion, installedVersion, matched),
        match_source: "name_match" as const,
      },
    ];
  });
}
