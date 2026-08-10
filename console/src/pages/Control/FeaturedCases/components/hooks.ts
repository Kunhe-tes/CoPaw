import { useCallback, useRef, useState } from "react";
import { featuredCasesApi } from "@/api/modules/featuredCases";
import type {
  FeaturedCase,
  FeaturedCaseCreate,
  FeaturedCaseUpdate,
} from "@/api/types/featuredCases";

interface ScopeCasesState {
  cases: FeaturedCase[];
  loading: boolean;
  total: number;
}

const EMPTY_SCOPE_STATE: ScopeCasesState = {
  cases: [],
  loading: false,
  total: 0,
};

export function useFeaturedCases(activeScopeBbkId: string) {
  const [scopeStates, setScopeStates] = useState<
    Record<string, ScopeCasesState>
  >({});
  const requestSequenceRef = useRef(0);
  const latestRequestByScopeRef = useRef<Record<string, number>>({});
  const activeScopeState = scopeStates[activeScopeBbkId] ?? EMPTY_SCOPE_STATE;

  const loadCases = useCallback(
    async (params: { bbk_id: string; page?: number; page_size?: number }) => {
      const scopeBbkId = params.bbk_id;
      const requestId = ++requestSequenceRef.current;
      latestRequestByScopeRef.current[scopeBbkId] = requestId;
      setScopeStates((current) => ({
        ...current,
        [scopeBbkId]: {
          ...(current[scopeBbkId] ?? EMPTY_SCOPE_STATE),
          loading: true,
        },
      }));
      try {
        const data = await featuredCasesApi.adminListCases(params);
        if (latestRequestByScopeRef.current[scopeBbkId] === requestId) {
          setScopeStates((current) => ({
            ...current,
            [scopeBbkId]: {
              cases: data.cases,
              loading: current[scopeBbkId]?.loading ?? true,
              total: data.total,
            },
          }));
        }
        return data;
      } catch (error) {
        console.error("Failed to load cases:", error);
        throw error;
      } finally {
        if (latestRequestByScopeRef.current[scopeBbkId] === requestId) {
          setScopeStates((current) => ({
            ...current,
            [scopeBbkId]: {
              ...(current[scopeBbkId] ?? EMPTY_SCOPE_STATE),
              loading: false,
            },
          }));
        }
      }
    },
    [],
  );

  const createCase = useCallback(async (caseItem: FeaturedCaseCreate) => {
    try {
      const result = await featuredCasesApi.adminCreateCase(caseItem);
      return result.data;
    } catch (error) {
      console.error("Failed to create case:", error);
      throw error;
    }
  }, []);

  const updateCase = useCallback(
    async (id: number, caseItem: Partial<FeaturedCaseUpdate>) => {
      try {
        const result = await featuredCasesApi.adminUpdateCase(id, caseItem);
        return result.data;
      } catch (error) {
        console.error("Failed to update case:", error);
        throw error;
      }
    },
    [],
  );

  const deleteCase = useCallback(async (id: number) => {
    try {
      await featuredCasesApi.adminDeleteCase(id);
    } catch (error) {
      console.error("Failed to delete case:", error);
      throw error;
    }
  }, []);

  const reorderCase = useCallback(async (id: number, sortOrder: number) => {
    try {
      const result = await featuredCasesApi.adminReorderCase(id, sortOrder);
      return result.data;
    } catch (error) {
      console.error("Failed to reorder case:", error);
      throw error;
    }
  }, []);

  return {
    cases: activeScopeState.cases,
    loading: activeScopeState.loading,
    total: activeScopeState.total,
    loadCases,
    createCase,
    updateCase,
    deleteCase,
    reorderCase,
  };
}
