const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  // Don't set Content-Type for FormData (browser sets boundary automatically)
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem("access_token");
    window.location.href = "/login";
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>("/api/v1/users/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (data: {
    email: string;
    password: string;
    full_name: string;
    stance?: string;
    weight_class?: string;
    experience_level?: string;
  }) =>
    request<{ id: string; email: string }>("/api/v1/users/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getMe: () =>
    request<import("./types").UserResponse>("/api/v1/users/me"),

  updateMe: (data: Record<string, unknown>) =>
    request<import("./types").UserResponse>("/api/v1/users/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Videos
  uploadVideo: (
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<import("./types").VideoUploadResponse> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/v1/videos/upload`);
      const token = getToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };

      xhr.onload = () => {
        if (xhr.status === 201) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          reject(new ApiError(xhr.status, xhr.statusText));
        }
      };
      xhr.onerror = () => reject(new Error("Upload failed"));

      const fd = new FormData();
      fd.append("file", file);
      xhr.send(fd);
    });
  },

  listVideos: (skip = 0, limit = 20) =>
    request<import("./types").VideoResponse[]>(
      `/api/v1/videos/?skip=${skip}&limit=${limit}`,
    ),

  getVideo: (id: string) =>
    request<import("./types").VideoResponse>(`/api/v1/videos/${id}`),

  trimVideo: (id: string, start_time: number, end_time: number) =>
    request<import("./types").VideoResponse>(`/api/v1/videos/${id}/trim`, {
      method: "PATCH",
      body: JSON.stringify({ start_time, end_time }),
    }),

  deleteVideo: (id: string) =>
    request<void>(`/api/v1/videos/${id}`, { method: "DELETE" }),

  // Media: <video src> can't send headers, so stream URLs are short-lived signed URLs
  signMediaUrl: async (
    resourceType: import("./types").MediaResourceType,
    resourceId: string,
  ): Promise<{ url: string; expiresAt: number }> => {
    const res = await request<import("./types").SignedMediaUrlResponse>(
      "/api/v1/media/sign",
      {
        method: "POST",
        body: JSON.stringify({ resource_type: resourceType, resource_id: resourceId }),
      },
    );
    return { url: `${API_BASE}${res.url}`, expiresAt: Date.parse(res.expires_at) };
  },

  // Analysis
  triggerAnalysis: (videoId: string) =>
    request<import("./types").AnalysisSessionResponse>(
      `/api/v1/videos/${videoId}/analyze`,
      { method: "POST" },
    ),

  listSessions: () =>
    request<import("./types").AnalysisSessionResponse[]>("/api/v1/sessions"),

  getSession: (id: string) =>
    request<import("./types").AnalysisSessionDetailResponse>(
      `/api/v1/sessions/${id}`,
    ),

  deleteSession: (sessionId: string) =>
    request<void>(`/api/v1/sessions/${sessionId}`, { method: "DELETE" }),

  submitFeedback: (sessionId: string, rating: string, comment?: string) =>
    request<import("./types").FeedbackResponse>(
      `/api/v1/sessions/${sessionId}/feedback`,
      {
        method: "POST",
        body: JSON.stringify({ rating, comment }),
      },
    ),

  disputeError: (sessionId: string, errorFlagId: string) =>
    request<{ status: string }>(
      `/api/v1/sessions/${sessionId}/dispute`,
      {
        method: "POST",
        body: JSON.stringify({ error_flag_id: errorFlagId }),
      },
    ),

  // YouTube
  searchYouTube: (query: string, maxResults = 10) =>
    request<{ url: string; title: string; duration: number | null; thumbnail: string | null; channel: string }[]>(
      "/api/v1/youtube/search",
      { method: "POST", body: JSON.stringify({ query, max_results: maxResults }) },
    ),

  downloadYouTube: (url: string) =>
    request<import("./types").VideoResponse>(
      "/api/v1/youtube/download",
      { method: "POST", body: JSON.stringify({ url }) },
    ),

  // Drills
  listDrills: (errorType?: string) =>
    request<import("./types").DrillResponse[]>(
      `/api/v1/drills/${errorType ? `?error_type=${errorType}` : ""}`,
    ),

  getSessionDrills: (sessionId: string) =>
    request<import("./types").DrillRecommendationResponse[]>(
      `/api/v1/drills/sessions/${sessionId}/recommendations`,
    ),
};

export { ApiError };
