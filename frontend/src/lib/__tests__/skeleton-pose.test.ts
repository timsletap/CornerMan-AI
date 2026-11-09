import { describe, expect, it } from "vitest";

import { uploadErrorMessage } from "../api";
import { GUARD_GAP_LIMIT, LOOP_MS, STILL_MS, guardGap, poseAt } from "../skeleton-pose";

describe("skeleton pose loop", () => {
  it("wraps without a jump at the loop boundary", () => {
    const end = poseAt(LOOP_MS - 1).pose;
    const start = poseAt(LOOP_MS).pose;
    expect(start).toEqual(poseAt(0).pose);
    expect(Math.abs(end.leadWrist[0] - start.leadWrist[0])).toBeLessThan(1);
  });

  it("extends the lead hand on the jab with the guard up", () => {
    const rest = poseAt(0);
    const jab = poseAt(STILL_MS);
    expect(jab.phase).toBe("jab");
    expect(jab.pose.leadWrist[0]).toBeGreaterThan(rest.pose.leadWrist[0] + 40);
    expect(guardGap(jab.pose, jab.phase)).toBeLessThan(GUARD_GAP_LIMIT);
  });

  it("drops the guard on the cross and recovers it at rest", () => {
    const cross = poseAt(1300);
    expect(cross.phase).toBe("cross");
    expect(guardGap(cross.pose, cross.phase)).toBeGreaterThan(GUARD_GAP_LIMIT);
    const rest = poseAt(2000);
    expect(guardGap(rest.pose, rest.phase)).toBeLessThan(GUARD_GAP_LIMIT);
  });
});

describe("uploadErrorMessage", () => {
  it("uses the server's detail when there is one", () => {
    expect(uploadErrorMessage(400, '{"detail":"File is not a valid video"}')).toBe(
      "File is not a valid video",
    );
  });

  it("falls back to a readable message for the status", () => {
    expect(uploadErrorMessage(413, "<html>too large</html>")).toMatch(/size limit/);
    expect(uploadErrorMessage(500, "")).toBe("Upload failed (500).");
    expect(uploadErrorMessage(422, '{"detail":[{"msg":"field required"}]}')).toBe(
      "Upload failed (422).",
    );
  });
});
