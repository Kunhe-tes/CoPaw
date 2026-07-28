import { describe, expect, it } from "vitest";
import {
  isSessionNotFoundError,
  shouldShowContentOnlySessionNotFound,
} from "./contentOnlySessionError";

describe("content-only session load errors", () => {
  it("recognizes the HTTP 404 error produced by the shared request layer", () => {
    const error = Object.assign(new Error("Chat not found"), { status: 404 });

    expect(isSessionNotFoundError(error)).toBe(true);
  });

  it("does not treat other failures as a missing session", () => {
    expect(
      isSessionNotFoundError(
        Object.assign(new Error("Server error"), { status: 500 }),
      ),
    ).toBe(false);
    expect(isSessionNotFoundError(new Error("Network error"))).toBe(false);
    expect(isSessionNotFoundError({ status: 404 })).toBe(false);
  });

  it("limits the not-found state to the active content-only session", () => {
    const error = Object.assign(new Error("Chat not found"), { status: 404 });

    expect(
      shouldShowContentOnlySessionNotFound({
        enabled: true,
        error,
        requestedSessionId: "chat-1",
        currentSessionId: "chat-1",
      }),
    ).toBe(true);
    expect(
      shouldShowContentOnlySessionNotFound({
        enabled: false,
        error,
        requestedSessionId: "chat-1",
        currentSessionId: "chat-1",
      }),
    ).toBe(false);
    expect(
      shouldShowContentOnlySessionNotFound({
        enabled: true,
        error,
        requestedSessionId: "chat-1",
        currentSessionId: "chat-2",
      }),
    ).toBe(false);
  });
});
