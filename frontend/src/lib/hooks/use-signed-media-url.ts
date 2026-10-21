"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MediaResourceType } from "@/lib/types";

// Re-sign slightly before the server-side expiry to absorb clock skew.
const EXPIRY_MARGIN_MS = 5_000;

interface Signed {
  key: string;
  url: string;
  expiresAt: number;
}

/**
 * Fetch a short-lived signed URL for a media resource (PLT-03).
 *
 * `refreshIfExpired` re-signs only when the current URL has expired, so a video error
 * caused by anything else (e.g. a missing file) does not loop.
 */
async function fetchSigned(
  resourceType: MediaResourceType,
  resourceId: string,
): Promise<Signed | null> {
  try {
    const res = await api.signMediaUrl(resourceType, resourceId);
    return { key: `${resourceType}:${resourceId}`, ...res };
  } catch {
    return null; // keep the previous URL; the player shows its own error state
  }
}

export function useSignedMediaUrl(resourceType: MediaResourceType, resourceId: string | null) {
  const key = resourceId ? `${resourceType}:${resourceId}` : null;
  const [signed, setSigned] = useState<Signed | null>(null);

  useEffect(() => {
    if (!resourceId) return;
    let cancelled = false;
    fetchSigned(resourceType, resourceId).then((s) => {
      if (s && !cancelled) setSigned(s);
    });
    return () => {
      cancelled = true;
    };
  }, [resourceType, resourceId]);

  const refreshIfExpired = useCallback(() => {
    if (!resourceId || !signed || signed.key !== key) return;
    if (Date.now() < signed.expiresAt - EXPIRY_MARGIN_MS) return;
    fetchSigned(resourceType, resourceId).then((s) => {
      if (s) setSigned(s);
    });
  }, [resourceType, resourceId, signed, key]);

  const url = signed && signed.key === key ? signed.url : null;
  return { url, refreshIfExpired };
}
