import { request } from "../request";
import type {
  CronAuthExpiryRequest,
  CronAuthExpiryResponse,
} from "../types/systemCheck";

export const systemCheckApi = {
  checkCronAuthExpiry: (body: CronAuthExpiryRequest) =>
    request<CronAuthExpiryResponse>("/system-check/cron-auth-expiry", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
