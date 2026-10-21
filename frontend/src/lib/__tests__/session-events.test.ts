import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import { api } from "../api";
import { subscribeToSessionEvents, toProgress } from "../session-events";

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.OPEN;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, ((e: { data: string }) => void)[]>();

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: (e: { data: string }) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }

  emit(type: string, data: unknown) {
    for (const fn of this.listeners.get(type) ?? []) fn({ data: JSON.stringify(data) });
  }

  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("session events", () => {
  let sign: MockInstance<typeof api.signMediaUrl>;

  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    let n = 0;
    sign = vi
      .spyOn(api, "signMediaUrl")
      .mockImplementation(async () => ({ url: `http://api/events?sig=${++n}`, expiresAt: 0 }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("maps event payloads to ProgressResponse", () => {
    expect(toProgress({ stage: "pose", pct: 0.3, message: "Pose" })).toEqual({
      step: "pose",
      progress: 0.3,
      detail: "Pose",
    });
  });

  it("signs an events URL, forwards progress, and closes on done", async () => {
    const onProgress = vi.fn();
    const onFinished = vi.fn();
    subscribeToSessionEvents("s1", { onProgress, onFinished });
    await flush();

    expect(sign).toHaveBeenCalledWith("events", "s1");
    const es = FakeEventSource.instances[0];
    expect(es.url).toBe("http://api/events?sig=1");

    es.emit("progress", { stage: "pose", pct: 0.5, message: "Pose" });
    expect(onProgress).toHaveBeenCalledWith({ step: "pose", progress: 0.5, detail: "Pose" });

    es.emit("done", { stage: "complete", pct: 1, message: "Analysis complete!" });
    expect(onFinished).toHaveBeenCalledWith("done", "Analysis complete!");
    expect(es.closed).toBe(true);
  });

  it("reports failure with the server message", async () => {
    const onFinished = vi.fn();
    subscribeToSessionEvents("s1", { onProgress: vi.fn(), onFinished });
    await flush();
    FakeEventSource.instances[0].emit("failed", { message: "Analysis failed: boom" });
    expect(onFinished).toHaveBeenCalledWith("failed", "Analysis failed: boom");
  });

  it("re-signs and reconnects when the browser gives up on the stream", async () => {
    vi.useFakeTimers();
    subscribeToSessionEvents("s1", { onProgress: vi.fn(), onFinished: vi.fn() });
    await vi.advanceTimersByTimeAsync(0);
    const first = FakeEventSource.instances[0];

    first.readyState = FakeEventSource.CLOSED; // e.g. reconnect got 403 after expiry
    first.onerror?.();
    await vi.advanceTimersByTimeAsync(2_000);

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].url).toBe("http://api/events?sig=2");
  });

  it("lets the browser retry transient errors on its own", async () => {
    vi.useFakeTimers();
    subscribeToSessionEvents("s1", { onProgress: vi.fn(), onFinished: vi.fn() });
    await vi.advanceTimersByTimeAsync(0);
    const es = FakeEventSource.instances[0];
    es.readyState = FakeEventSource.CONNECTING;
    es.onerror?.();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("stop closes the stream and cancels pending reconnects", async () => {
    vi.useFakeTimers();
    const stop = subscribeToSessionEvents("s1", { onProgress: vi.fn(), onFinished: vi.fn() });
    await vi.advanceTimersByTimeAsync(0);
    const es = FakeEventSource.instances[0];
    es.readyState = FakeEventSource.CLOSED;
    es.onerror?.();
    stop();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
