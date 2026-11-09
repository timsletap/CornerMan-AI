"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { VideoUploadZone } from "@/components/video/video-upload-zone";
import { SectionHeading } from "@/components/ui/card";

const TIPS = [
  {
    title: "Whole body in frame",
    body: "Head to feet, the entire round. The tracker needs your shoulders, hips, and hands to read a punch.",
  },
  {
    title: "Side-on or three-quarter",
    body: "Set the camera at chest height, off to one side. Straight-on hides how far your punches extend.",
  },
  {
    title: "Keep the camera still",
    body: "A tripod or a bag against the wall beats a friend holding the phone. Camera shake reads as movement.",
  },
  {
    title: "One fighter is tracked",
    body: "With two people in frame, CornerMan follows the one who is larger and closer to the middle.",
  },
];

export default function UploadPage() {
  const router = useRouter();

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <SectionHeading eyebrow="New breakdown" title="Upload your film" />

      <VideoUploadZone
        onDone={(videoId, sessionId) =>
          router.push(sessionId ? `/sessions/${sessionId}` : `/videos/${videoId}`)
        }
      />

      <section>
        <p className="eyebrow mb-4 text-chalk">Film it right, get a better read</p>
        <div className="grid gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          {TIPS.map((tip, i) => (
            <div key={tip.title} className="bg-panel p-5">
              <p className="font-mono text-xs text-blood">0{i + 1}</p>
              <h3 className="display mt-2 text-xl text-chalk">{tip.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-mute">{tip.body}</p>
            </div>
          ))}
        </div>
        <p className="mt-5 text-sm text-mute">
          No clip of your own handy?{" "}
          <Link href="/search" className="text-chalk underline decoration-blood underline-offset-4 hover:text-blood">
            Import one from YouTube
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
