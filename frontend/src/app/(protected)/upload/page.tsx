"use client";

import { useRouter } from "next/navigation";
import { VideoUploadZone } from "@/components/video/video-upload-zone";

export default function UploadPage() {
  const router = useRouter();

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Upload Video</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Upload your sparring or training footage for AI analysis.
        </p>
      </div>
      <VideoUploadZone onUploaded={(id) => router.push(`/videos/${id}`)} />
    </div>
  );
}
