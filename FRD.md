# Functional Requirements Document (FRD)
## Project Name: CornerMan AI (MMA/Striking Analysis Platform)
**Version:** 2.0
**Date:** February 6, 2026
**Status:** Draft / Ready for Dev Review

---

## 1. Executive Summary
**CornerMan AI** is an advanced coaching platform designed for combat sports practitioners (MMA, Boxing, Muay Thai). It leverages a hybrid AI architecture combining **Computer Vision (CV)** for quantitative biomechanical analysis and **Agentic LLMs** for qualitative coaching. The system ingests user-uploaded sparring/training footage, extracts performance metrics (speed, guard integrity, telegraphing), and delivers personalized, actionable feedback through an AI persona.

## 2. Scope
### 2.1 In Scope
* **User Management:** Authentication, profile creation (stance, weight class, experience level).
* **Video Ingestion:** Upload handling, compression, and validation of fight clips.
* **Pipeline A (Vision):** Frame-by-frame pose estimation, hit detection, velocity calculation, and error flagging.
* **Pipeline B (Agentic):** LLM integration for "Coach Persona" synthesis, utilizing vision data to generate advice.
* **Data Visualization:** Interactive dashboards showing strikes, errors, and trends.
* **Drill Recommendation:** Mapping identified errors to specific corrective drills.

### 2.2 Out of Scope (Phase 1)
* Live/Real-time streaming analysis.
* Social sharing features.
* Wearable sensor integration.
* Billing/Subscription management (Stubbed only).

---

## 3. User Personas
1.  **The Fighter (User):** Hobbyist to Pro. Uploads video to find holes in their game.
2.  **The Coach (Admin/User):** Uses the tool to analyze students.
3.  **The Developer (Admin):** Manages API keys, monitors pipeline costs and error logs.

---

## 4. Functional Requirements

### 4.1 System Architecture Overview
The system follows a microservices approach:
1.  **Frontend:** React/Next.js (Mobile-First).
2.  **API Gateway:** Managing requests (FastAPI).
3.  **Processing Queue:** Asynchronous handling (Celery/Redis).
4.  **Vision Engine:** Python + MediaPipe/YOLOv8.
5.  **Coaching Agent:** LLM Wrapper (OpenAI/Gemini/Claude).
6.  **Database:** PostgreSQL (User data) + S3 (Video storage).

### 4.2 Module 1: Video Ingestion & Management
| ID | Requirement | Acceptance Criteria | Priority |
| :--- | :--- | :--- | :--- |
| **VID-01** | **Video Upload** | User can upload `.mp4`, `.mov` files up to 500MB via drag-and-drop. | High |
| **VID-02** | **Validation** | System rejects non-video files or corrupted files immediately. | High |
| **VID-03** | **Trimming** | User can select a specific `start_time` and `end_time` (max 60s) before processing. | Med |
| **VID-04** | **Storage** | Original video is stored in S3 bucket; metadata stored in SQL. | High |

### 4.3 Module 2: The Vision Engine (The "Eyes")
*Technical Stack: Python, OpenCV, MediaPipe Pose (or YOLOv8-Pose)*

| ID | Requirement | Acceptance Criteria | Priority |
| :--- | :--- | :--- | :--- |
| **VIS-01** | **Skeleton Tracking** | Extract 33 distinct body landmarks (wrist, elbow, shoulder, hip, nose). | Critical |
| **VIS-02** | **Strike Detection** | Identify "Strike Events" based on velocity spikes of wrist keypoints (> threshold). | Critical |
| **VIS-03** | **Guard Analysis** | For every strike frame, calc distance between `Off-Hand Wrist` and `Nose`. If > 15cm, flag `Error: Dropped Guard`. | High |
| **VIS-04** | **Telegraph Detection** | Analyze 10 frames *pre-strike*. If `Elbow X-coord` varies > 10% before motion, flag `Error: Chicken Wing`. | High |
| **VIS-05** | **Output JSON** | Generate structured JSON with timestamps, strike types, and error flags. | Critical |
| **VIS-06** | **Subject Isolation** | Identify "Primary Actor" by tracking the skeleton closest to frame center with largest bounding box. Ignore background skeletons. | Critical |
| **VIS-07** | **Occlusion Handling** | If Primary Actor is occluded > 0.5s, pause analysis; resume when confidence > 0.7. | High |

### 4.4 Module 3: The Coaching Agent (The "Brain")
*Technical Stack: LangChain / OpenAI API / Gemini API*

| ID | Requirement | Acceptance Criteria | Priority |
| :--- | :--- | :--- | :--- |
| **AGT-01** | **Context Ingestion** | System sends **Vision JSON** + **User Profile** to the LLM. | Critical |
| **AGT-02** | **Persona Prompting** | LLM acts as "CornerMan": direct, technical, encouraging. No "As an AI..." disclaimers. | High |
| **AGT-03** | **Drill Mapping** | Map `Error: Dropped Guard` to predefined drills (e.g., "Wall Touch Drill") in vector DB. | High |
| **AGT-04** | **Response Structure** | Output: 1. Summary, 2. Key Metric, 3. The "One Thing" to fix, 4. Prescribed Drill. | High |

### 4.5 Module 4: User Interface (Frontend)
| ID | Requirement | Acceptance Criteria | Priority |
| :--- | :--- | :--- | :--- |
| **UI-01** | **Dashboard** | Video player left, metrics right. Sync video playback with scrolling metrics. | High |
| **UI-02** | **Annotation Overlay** | Overlay simplified skeleton. Draw **RED** lines on limbs when error is flagged. | Med |
| **UI-03** | **Feedback Loop** | Include Thumbs Up/Down icon next to coaching tips. | Low |
| **UI-04** | **Dispute Flag** | If user marks error as "Incorrect," flag timestamp for manual review. | Low |

### 4.6 Module 5: Constraints & Quotas
| ID | Requirement | Acceptance Criteria | Priority |
| :--- | :--- | :--- | :--- |
| **LIM-01** | **Duration Limit** | MVP restriction: Videos strictly limited to **60 seconds** max. | Critical |
| **LIM-02** | **Usage Tiering** | "Free Tier": 3 uploads/day. "Pro Tier": Unlimited. | High |
| **LIM-03** | **Circuit Breaker** | If user consumes > $5.00 API credits in 1 hour, auto-suspend processing. | Med |

---

## 5. Non-Functional Requirements (NFRs)
1.  **Performance:** Processing time max 2x video length (30s video takes 60s to analyze).
2.  **Accuracy:** Strike detection >85% recall against "Golden Dataset" (20 manually labeled clips).
3.  **Mobile-First:** UI must stack vertically on screens < 768px (iOS Safari/Android Chrome).
4.  **Privacy:** Data encrypted at rest (AES-256).

---

## 6. Data Models (Simplified Schema)

### 6.1 `Analysis_Session`
```json
{
  "session_id": "uuid",
  "user_id": "uuid",
  "video_url": "s3://...",
  "status": "completed",
  "metrics": { "total_strikes": 42, "avg_velocity": 8.5, "guard_score": 75 },
  "coach_feedback": "Good volume, but watch the right hand...",
  "created_at": "timestamp"
}