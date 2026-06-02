export interface HtmlPreviewClickEventPayload {
  source_id?: string | null;
  user_id?: string | null;
  bbk_id?: string | null;
  cron_task_id?: string | null;
  cron_task_name?: string | null;
  file_url: string;
  file_name?: string | null;
  list_key?: string | null;
  list_name?: string | null;
  button_id?: string | null;
  button_name?: string | null;
  button_text?: string | null;
  button_type?: "insight" | "phone" | "plan" | "other" | string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  customer_info?: Record<string, string> | null;
  clicked_at?: string | null;
}

export interface HtmlPreviewClickSubmitResponse {
  success: boolean;
}

export interface HtmlPreviewClickSummaryItem {
  button_label: string;
  button_id?: string | null;
  button_name?: string | null;
  button_text?: string | null;
  bbk_id?: string | null;
  cron_task_id?: string | null;
  cron_task_name?: string | null;
  list_key?: string | null;
  list_name?: string | null;
  file_url?: string | null;
  file_name?: string | null;
  click_count: number;
  last_clicked_at?: string | null;
}

export interface HtmlPreviewClickSummaryResponse {
  success: boolean;
  items: HtmlPreviewClickSummaryItem[];
}

export interface HtmlPreviewClickEventItem {
  id: number;
  source_id?: string | null;
  user_id?: string | null;
  bbk_id?: string | null;
  cron_task_id?: string | null;
  cron_task_name?: string | null;
  file_url: string;
  file_name?: string | null;
  list_key?: string | null;
  list_name?: string | null;
  button_id?: string | null;
  button_name?: string | null;
  button_text?: string | null;
  button_type?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  customer_info?: Record<string, string> | null;
  clicked_at?: string | null;
}

export interface HtmlPreviewClickEventListResponse {
  success: boolean;
  items: HtmlPreviewClickEventItem[];
}

export interface HtmlPreviewCustomerClickSummaryItem {
  customer_id?: string | null;
  customer_name: string;
  insight_count: number;
  phone_count: number;
  plan_count: number;
  total_click_count: number;
  last_clicked_at?: string | null;
}

export interface HtmlPreviewCustomerClickSummaryResponse {
  success: boolean;
  items: HtmlPreviewCustomerClickSummaryItem[];
}

export interface HtmlPreviewListSnapshotCustomer {
  customer_id?: string | null;
  customer_name: string;
  extra_info?: Record<string, string> | null;
}

export interface HtmlPreviewListSnapshotPayload {
  source_id?: string | null;
  bbk_id?: string | null;
  cron_task_id?: string | null;
  cron_task_name?: string | null;
  list_key?: string | null;
  list_name?: string | null;
  file_url: string;
  file_name?: string | null;
  customers: HtmlPreviewListSnapshotCustomer[];
  snapshot_at?: string | null;
}

export interface HtmlPreviewListSnapshotResponse {
  success: boolean;
  customer_count: number;
}

export interface HtmlPreviewListSummaryItem {
  list_key: string;
  list_name: string;
  file_url?: string | null;
  file_name?: string | null;
  cron_task_id?: string | null;
  cron_task_name?: string | null;
  customer_count: number;
  clicked_customer_count: number;
  insight_count: number;
  phone_count: number;
  plan_count: number;
  total_click_count: number;
  last_clicked_at?: string | null;
}

export interface HtmlPreviewListSummaryResponse {
  success: boolean;
  items: HtmlPreviewListSummaryItem[];
}

export interface HtmlPreviewCustomerClickItem {
  customer_id?: string | null;
  customer_name: string;
  list_key?: string | null;
  list_name?: string | null;
  insight_count: number;
  phone_count: number;
  plan_count: number;
  total_click_count: number;
  last_clicked_at?: string | null;
}

export interface HtmlPreviewCustomerClickResponse {
  success: boolean;
  items: HtmlPreviewCustomerClickItem[];
}
