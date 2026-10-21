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

  it("signs media URLs via POST and returns an absolute URL with no token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        url: "/api/v1/videos/v1/stream?exp=2000000000&sig=abc",
        expires_at: "2033-05-18T03:33:20Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const signed = await api.signMediaUrl("video", "v1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/media\/sign$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ resource_type: "video", resource_id: "v1" });
    expect(signed.url).toMatch(/^https?:\/\/.+\/api\/v1\/videos\/v1\/stream\?exp=2000000000&sig=abc$/);
    expect(signed.url).not.toContain("token");
    expect(signed.expiresAt).toBe(2_000_000_000_000);
  });
});
