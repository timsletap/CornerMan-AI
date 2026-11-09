"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ThumbIcon } from "@/components/ui/icons";

type Rating = "thumbs_up" | "thumbs_down";

interface Props {
  sessionId: string;
}

export function FeedbackButtons({ sessionId }: Props) {
  const [submitted, setSubmitted] = useState<Rating | null>(null);
  const [failed, setFailed] = useState(false);

  async function handleFeedback(rating: Rating) {
    setFailed(false);
    try {
      await api.submitFeedback(sessionId, rating);
      setSubmitted(rating);
    } catch {
      setFailed(true);
    }
  }

  if (submitted) {
    return <p className="text-sm text-mute">Thanks for the feedback.</p>;
  }

  const buttonClass =
    "flex h-9 w-9 cursor-pointer items-center justify-center border border-line-2 text-mute transition-colors hover:border-chalk/60 hover:text-chalk";

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-mute">
        {failed ? "That didn't send. Try again?" : "Was this advice useful?"}
      </span>
      <button className={buttonClass} aria-label="Yes, useful" onClick={() => handleFeedback("thumbs_up")}>
        <ThumbIcon />
      </button>
      <button className={buttonClass} aria-label="No, not useful" onClick={() => handleFeedback("thumbs_down")}>
        <ThumbIcon down />
      </button>
    </div>
  );
}
