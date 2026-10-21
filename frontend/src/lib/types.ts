// Enums matching backend models

export type Stance = "orthodox" | "southpaw" | "switch";
export type WeightClass =
  | "strawweight"
  | "flyweight"
  | "bantamweight"
  | "featherweight"
  | "lightweight"
  | "welterweight"
  | "middleweight"
  | "light_heavyweight"
  | "heavyweight";
export type ExperienceLevel = "beginner" | "intermediate" | "advanced" | "pro";
export type UserTier = "free" | "pro";
export type UserRole = "fighter" | "coach" | "admin";

export type VideoStatus =
  | "uploaded"
  | "validating"
  | "validated"
  | "queued"
  | "processing"
  | "completed"
  | "failed";
export type AnalysisStatus = "queued" | "processing" | "completed" | "failed";
export type StrikeType =
  | "jab"
  | "cross"
  | "hook"
  | "uppercut"
  | "body_shot"
  | "elbow"
  | "knee"
  | "kick"
  | "other";
export type Hand = "left" | "right";
export type ErrorType = "dropped_guard" | "chicken_wing" | "other";
export type Severity = "low" | "medium" | "high";
export type Rating = "thumbs_up" | "thumbs_down";

// Response types matching backend Pydantic schemas

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  stance: Stance | null;
  weight_class: WeightClass | null;
  experience_level: ExperienceLevel | null;
  tier: UserTier;
  role: UserRole;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface VideoResponse {
  id: string;
  user_id: string;
  original_filename: string;
  s3_url: string | null;
  file_size_bytes: number;
  duration_seconds: number | null;
  format: string;
  trim_start: number | null;
  trim_end: number | null;
  status: VideoStatus;
  created_at: string;
}

export interface VideoUploadResponse {
  id: string;
  original_filename: string;
  file_size_bytes: number;
  format: string;
  status: VideoStatus;
  created_at: string;
}

export interface StrikeEventResponse {
  id: string;
  timestamp_ms: number;
  frame_number: number;
  strike_type: StrikeType;
  hand: Hand;
  velocity: number | null;
  keypoints: Record<string, { x: number; y: number; confidence: number }> | null;
}

export interface ErrorFlagResponse {
  id: string;
  strike_event_id: string | null;
  error_type: ErrorType;
  timestamp_ms: number;
  frame_number: number;
  severity: Severity;
  details: Record<string, unknown> | null;
  user_disputed: boolean;
}

export interface DrillResponse {
  id: string;
  name: string;
  description: string;
  error_type: string;
  difficulty_level: number;
  video_url: string | null;
}

export interface DrillRecommendationResponse {
  id: string;
  drill: DrillResponse;
  priority: number;
}

export interface AnalysisSessionResponse {
  id: string;
  user_id: string;
  video_id: string;
  status: AnalysisStatus;
  total_strikes: number | null;
  avg_velocity: number | null;
  guard_score: number | null;
  coach_feedback: string | null;
  annotated_video_path: string | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  created_at: string;
}

export interface VisionJson {
  video_metadata: {
    fps: number;
    total_frames: number;
    duration_seconds: number;
    resolution: { width: number; height: number };
  };
  frames_analyzed: number;
  metrics: {
    total_strikes: number;
    avg_velocity: number;
    guard_score: number;
    strikes_per_minute: number;
    error_counts: Record<string, number>;
  };
  annotated_video_path: string | null;
}

export interface AnalysisSessionDetailResponse extends AnalysisSessionResponse {
  vision_json: VisionJson | null;
  strike_events: StrikeEventResponse[];
  error_flags: ErrorFlagResponse[];
  drill_recommendations: DrillRecommendationResponse[];
}

export interface ProgressResponse {
  step: string;
  progress: number;
  detail: string;
}

export interface CoachingFeedback {
  summary: string;
  key_metric: string;
  one_thing: string;
  prescribed_drill: { error_type: string; reasoning: string };
  detailed_notes: string[];
}

export interface FeedbackResponse {
  id: string;
  session_id: string;
  rating: Rating;
  comment: string | null;
  created_at: string;
}

export type MediaResourceType = "video" | "annotated";

export interface SignedMediaUrlResponse {
  url: string;
  expires_at: string;
}
