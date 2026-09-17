import { Layout } from "antd";
// import ThemeToggleButton from "../components/ThemeToggleButton";
import styles from "./index.module.less";
import { useTheme } from "../contexts/ThemeContext";
import { useBrandTheme } from "../contexts/BrandThemeContext";

const { Header: AntHeader } = Layout;

export default function Header() {
  const { isDark } = useTheme();
  // 获取动态品牌配置，用于显示正确的 logo
  const { theme: brandTheme } = useBrandTheme();

  return (
    <>
      <AntHeader className={styles.header}>
        <div className={styles.logoWrapper}>
          {/* ==================== 品牌主题 (Kun He) ==================== */}
          {/* 使用动态品牌 logo，根据 source 和明暗主题切换 */}
          <img
            src={
              isDark
                ? `${import.meta.env.BASE_URL}${brandTheme.darkLogo.replace(
                    /^\//,
                    "",
                  )}`
                : `${import.meta.env.BASE_URL}${brandTheme.logo.replace(
                    /^\//,
                    "",
                  )}`
            }
            alt={brandTheme.brandName}
            className={styles.logoImg}
          />
          {/* ==================== 品牌主题结束 ==================== */}
        </div>
      </AntHeader>
    </>
  );
}
