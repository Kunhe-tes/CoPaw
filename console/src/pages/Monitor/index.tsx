import { Routes, Route } from "react-router-dom";
import CronOverviewPage from "./CronOverview";
import CronBatchDispatchPage from "./CronBatchDispatch";
import TaskCenterPage from "./TaskCenter";

export default function MonitorPage() {
  return (
    <Routes>
      <Route path="/" element={<CronOverviewPage />} />
      <Route path="/cron-overview" element={<CronOverviewPage />} />
      <Route path="/cron-batch-dispatch" element={<CronBatchDispatchPage />} />
      <Route path="/tasks" element={<TaskCenterPage />} />
    </Routes>
  );
}
