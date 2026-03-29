"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { trackEvent } from "@/lib/activity";
import type { Video, ProcessingJob } from "@/types";

export default function VideoDetailPage() {
  const params = useParams();
  const videoId = params.id as string;
  const [video, setVideo] = useState<Video | null>(null);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    trackEvent("page_view", { page: "video_detail", video_id: videoId });
    api.videos
      .get(videoId)
      .then((v) => setVideo(v as Video))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load video"));
    api.jobs
      .listByVideo(videoId)
      .then((j) => setJobs(j as ProcessingJob[]))
      .catch(() => {});
  }, [videoId]);

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <div className="p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-300">{error}</div>
        <Link href="/dashboard" className="mt-4 inline-block text-orange-400 hover:text-orange-300">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-8">
      <Link href="/dashboard" className="text-sm text-orange-400 hover:text-orange-300 mb-4 inline-block">
        &larr; Back to Dashboard
      </Link>

      <h1 className="text-3xl font-bold mb-2">{video.title}</h1>
      {video.opponent && <p className="text-gray-400 mb-1">vs {video.opponent}</p>}
      {video.game_date && (
        <p className="text-sm text-gray-500 mb-6">{new Date(video.game_date).toLocaleDateString()}</p>
      )}

      <div className="p-4 bg-gray-900 rounded-lg border border-gray-700 mb-8">
        <div className="text-sm text-gray-400">File</div>
        <div className="text-sm">{video.file_key || "No file uploaded"}</div>
        {video.duration_seconds && (
          <div className="text-sm text-gray-400 mt-1">
            Duration: {Math.floor(video.duration_seconds / 60)}m {video.duration_seconds % 60}s
          </div>
        )}
      </div>

      <h2 className="text-xl font-semibold mb-4">Processing Jobs</h2>
      {jobs.length === 0 ? (
        <p className="text-gray-500">No processing jobs for this video.</p>
      ) : (
        <div className="space-y-2">
          {jobs.map((job) => (
            <Link
              key={job.id}
              href={`/jobs/${job.id}`}
              className="flex items-center justify-between p-4 bg-gray-900 rounded-lg border border-gray-700 hover:bg-gray-800 transition-colors"
            >
              <div>
                <div className="text-sm font-medium">Job {job.id.slice(0, 8)}...</div>
                <div className="text-xs text-gray-400">{new Date(job.created_at).toLocaleString()}</div>
              </div>
              <div className="flex items-center gap-3">
                {job.highlights_count !== null && (
                  <span className="text-xs text-gray-400">{job.highlights_count} highlights</span>
                )}
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    job.status === "completed"
                      ? "bg-green-900 text-green-300"
                      : job.status === "processing"
                      ? "bg-yellow-900 text-yellow-300"
                      : job.status === "failed"
                      ? "bg-red-900 text-red-300"
                      : "bg-gray-800 text-gray-400"
                  }`}
                >
                  {job.status}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
