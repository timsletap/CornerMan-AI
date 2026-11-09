"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { formatClock } from "@/lib/format";
import { MAX_DURATION_SECONDS } from "@/lib/upload-rules";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/card";
import { SearchIcon } from "@/components/ui/icons";
import { ErrorNote, LoadingBlock } from "@/components/ui/spinner";

interface SearchResult {
  url: string;
  title: string;
  duration: number | null;
  thumbnail: string | null;
  channel: string;
}

const SUGGESTIONS = [
  "heavy bag boxing combinations",
  "muay thai pad work",
  "shadow boxing drills",
  "UFC fight highlights",
];

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function search(text: string) {
    if (!text.trim()) return;
    setQuery(text);
    setSearching(true);
    setError("");
    try {
      setResults(await api.searchYouTube(text));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    search(query);
  }

  async function handleImport(url: string) {
    setDownloading(url);
    setError("");
    try {
      const video = await api.downloadYouTube(url);
      router.push(`/videos/${video.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
      setDownloading(null);
    }
  }

  const limitMinutes = MAX_DURATION_SECONDS / 60;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <SectionHeading eyebrow="Scout" title="Find clips to break down" />
        <p className="mt-3 max-w-2xl text-mute">
          Search YouTube and import a clip into your library. Clips can be up to{" "}
          {limitMinutes} minutes. One fighter filmed from the side reads best.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <div className="flex-1">
          <Input
            aria-label="Search YouTube"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for training or fight footage"
          />
        </div>
        <Button type="submit" disabled={searching || !query.trim()} className="h-11">
          <SearchIcon /> {searching ? "Searching" : "Search"}
        </Button>
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <span className="eyebrow">Try</span>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => search(s)}
            className="cursor-pointer rounded-sm border border-line-2 px-3 py-1 text-sm text-mute transition-colors hover:border-chalk/60 hover:text-chalk"
          >
            {s}
          </button>
        ))}
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {searching && <LoadingBlock />}

      {!searching && results !== null && results.length === 0 && (
        <p className="text-mute">Nothing came back for that search. Try different words.</p>
      )}

      {!searching && results && results.length > 0 && (
        <ul className="space-y-3">
          {results.map((r) => {
            const tooLong = r.duration !== null && r.duration > MAX_DURATION_SECONDS;
            const importing = downloading === r.url;
            return (
              <li
                key={r.url}
                className="flex flex-wrap items-center gap-4 rounded-md border border-line bg-panel/85 p-4 sm:flex-nowrap"
              >
                {r.thumbnail && (
                  // YouTube thumbnails come from many hosts; a plain img avoids listing them all
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={r.thumbnail}
                    alt=""
                    className="h-20 w-36 shrink-0 rounded-sm object-cover"
                  />
                )}
                <div className="min-w-0 flex-1 basis-48">
                  <h3 className="line-clamp-2 font-medium text-chalk">{r.title}</h3>
                  <p className="mt-1 font-mono text-xs text-dim">
                    {r.channel} · {r.duration === null ? "length unknown" : formatClock(r.duration * 1000)}
                  </p>
                  {tooLong && (
                    <p className="mt-1 text-xs text-gold">
                      Over the {limitMinutes} minute limit
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  variant={tooLong ? "ghost" : "primary"}
                  disabled={downloading !== null || tooLong}
                  onClick={() => handleImport(r.url)}
                >
                  {importing ? "Importing..." : "Import"}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
