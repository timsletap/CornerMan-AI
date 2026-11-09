import { describe, expect, it } from "vitest";

import {
  canUpload,
  checkClip,
  MAX_DURATION_SECONDS,
  MAX_UPLOAD_BYTES,
  type ClipFacts,
} from "../upload-rules";

const good: ClipFacts = {
  name: "sparring.mp4",
  type: "video/mp4",
  sizeBytes: 40 * 1024 * 1024,
  durationSeconds: 45,
  width: 1920,
  height: 1080,
};

function statusOf(facts: ClipFacts, id: string) {
  return checkClip(facts).find((c) => c.id === id)?.status;
}

describe("checkClip", () => {
  it("passes a normal landscape clip", () => {
    const checks = checkClip(good);
    expect(checks.map((c) => c.status)).toEqual(["pass", "pass", "pass", "pass", "pass"]);
    expect(canUpload(checks)).toBe(true);
  });

  it("blocks unsupported formats", () => {
    const facts = { ...good, name: "clip.avi", type: "video/x-msvideo" };
    expect(statusOf(facts, "format")).toBe("fail");
    expect(canUpload(checkClip(facts))).toBe(false);
  });

  it("accepts .mov by extension even when the browser reports no MIME type", () => {
    expect(statusOf({ ...good, name: "IMG_0042.MOV", type: "" }, "format")).toBe("pass");
  });

  it("blocks files over the size limit but allows one exactly at it", () => {
    expect(statusOf({ ...good, sizeBytes: MAX_UPLOAD_BYTES }, "size")).toBe("pass");
    expect(statusOf({ ...good, sizeBytes: MAX_UPLOAD_BYTES + 1 }, "size")).toBe("fail");
  });

  it("blocks clips over the length limit but allows one exactly at it", () => {
    expect(statusOf({ ...good, durationSeconds: MAX_DURATION_SECONDS }, "length")).toBe("pass");
    expect(statusOf({ ...good, durationSeconds: MAX_DURATION_SECONDS + 1 }, "length")).toBe(
      "fail",
    );
  });

  it("only warns when the browser cannot read the clip", () => {
    const facts = { ...good, durationSeconds: null, width: null, height: null };
    const checks = checkClip(facts);
    expect(checks.map((c) => c.id)).toEqual(["format", "size", "length"]);
    expect(statusOf(facts, "length")).toBe("warn");
    expect(canUpload(checks)).toBe(true);
  });

  it("warns on portrait and low resolution clips without blocking", () => {
    const facts = { ...good, width: 360, height: 640 };
    expect(statusOf(facts, "framing")).toBe("warn");
    expect(statusOf(facts, "resolution")).toBe("warn");
    expect(canUpload(checkClip(facts))).toBe(true);
  });
});
