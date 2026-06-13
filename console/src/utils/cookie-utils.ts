// 该文件需单独替换
export function getWPlusCookie(name: string): string | null {
  const cookies = document.cookie.split(";").map((c) => c.trim());
  for (const cookie of cookies) {
    const [key, value] = cookie.split("=");
    if (key === name) {
      return value ?? null;
    }
  }
  return null;
}
