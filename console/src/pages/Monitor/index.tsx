import { Routes, Route } from "react-router-dom";
import CronOverviewPage from "./CronOverview";
import CronBatchDispatchPage from "./CronBatchDispatch";

export default function MonitorPage() {
  return (
    <Routes>
      <Route path="/" element={<CronOverviewPage />} />
      <Route path="/cron-overview" element={<CronOverviewPage />} />
      <Route path="/cron-batch-dispatch" element={<CronBatchDispatchPage />} />
    </Routes>
  );
}
