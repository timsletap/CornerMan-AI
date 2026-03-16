"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface Props {
  sessionId: string;
}

export function FeedbackButtons({ sessionId }: Props) {
  const [submitted, setSubmitted] = useState<"thumbs_up" | "thumbs_down" | null>(null);

  async function handleFeedback(rating: "thumbs_up" | "thumbs_down") {
    try {
      await api.submitFeedback(sessionId, rating);
      setSubmitted(rating);
    } catch {
      // ignore
    }
  }

  if (submitted) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-400">
        <span>{submitted === "thumbs_up" ? "\u{1F44D}" : "\u{1F44E}"}</span>
        <span>Feedback submitted. Thanks!</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-zinc-400">Was this helpful?</span>
      <Button variant="outline" size="sm" onClick={() => handleFeedback("thumbs_up")}>
        {"\u{1F44D}"}
      </Button>
      <Button variant="outline" size="sm" onClick={() => handleFeedback("thumbs_down")}>
        {"\u{1F44E}"}
      </Button>
    </div>
  );
}
