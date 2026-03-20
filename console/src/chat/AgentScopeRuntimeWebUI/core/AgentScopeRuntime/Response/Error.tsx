import { IAgentScopeRuntimeError, IAgentScopeRuntimeMessage } from "../types";
import { Bubble } from "@/chat";


export default function Error({ data }: { data: IAgentScopeRuntimeError | IAgentScopeRuntimeMessage }) {
  return <Bubble.Interrupted type="error" title={data.code} desc={data.message} />;
}