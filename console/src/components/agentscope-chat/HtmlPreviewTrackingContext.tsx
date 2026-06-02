import React, { createContext, useContext } from "react";

export interface HtmlPreviewTrackingContextValue {
  cronTaskId?: string | null;
  cronTaskName?: string | null;
}

const defaultValue: HtmlPreviewTrackingContextValue = {};

const HtmlPreviewTrackingContext =
  createContext<HtmlPreviewTrackingContextValue>(defaultValue);

export function HtmlPreviewTrackingProvider(props: {
  value: HtmlPreviewTrackingContextValue;
  children: React.ReactNode;
}) {
  return (
    <HtmlPreviewTrackingContext.Provider value={props.value}>
      {props.children}
    </HtmlPreviewTrackingContext.Provider>
  );
}

export function useHtmlPreviewTracking(): HtmlPreviewTrackingContextValue {
  return useContext(HtmlPreviewTrackingContext);
}
