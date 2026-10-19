import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed JSON body on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { id: "u1", email: "a@b.c" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.getMe()).resolves.toEqual({ id: "u1", email: "a@b.c" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/users\/me$/);
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("throws with the server's detail message on error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(404, { detail: "Not found" })));

    await expect(api.getMe()).rejects.toThrow("Not found");
  });
});
