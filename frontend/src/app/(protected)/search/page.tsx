"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

interface SearchResult {
  url: string;
  title: string;
  duration: number | null;
  thumbnail: string | null;
  channel: string;
}

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("UFC fight highlights");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError("");
    try {
      const res = await api.searchYouTube(query);
      setResults(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  async function handleDownload(url: string) {
    setDownloading(url);
    setError("");
    try {
      const video = await api.downloadYouTube(url);
      router.push(`/videos/${video.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
      setDownloading(null);
    }
  }

  function formatDuration(secs: number | null) {
    if (!secs) return "--";
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Find Fight Clips</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Search YouTube for UFC fight clips to analyze. Clips must be under 60 seconds.
        </p>
      </div>

      <form onSubmit={handleSearch} className="flex gap-3">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for fight clips..."
          className="flex-1"
        />
        <Button type="submit" disabled={searching}>
          {searching ? "Searching..." : "Search"}
        </Button>
      </form>

      {error && (
        <div className="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {searching && (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      )}

      <div className="space-y-3">
        {results.map((r) => {
          const tooLong = r.duration !== null && r.duration > 60;
          return (
            <Card key={r.url} className="flex items-start gap-4">
              {r.thumbnail && (
                <img
                  src={r.thumbnail}
                  alt={r.title}
                  className="w-32 h-20 object-cover rounded-lg flex-shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-medium text-white truncate">{r.title}</h3>
                <p className="text-xs text-zinc-500 mt-0.5">{r.channel}</p>
                <p className="text-xs text-zinc-400 mt-1">
                  Duration: {formatDuration(r.duration)}
                  {tooLong && <span className="text-red-400 ml-2">(exceeds 60s limit)</span>}
                </p>
              </div>
              <Button
                size="sm"
                variant={tooLong ? "ghost" : "primary"}
                disabled={downloading === r.url || tooLong}
                onClick={() => handleDownload(r.url)}
              >
                {downloading === r.url ? "Downloading..." : "Import"}
              </Button>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
