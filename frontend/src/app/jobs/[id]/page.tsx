"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ProcessingJob, Highlight, Stat } from "@/types";
import ClipPlayer from "@/components/video/ClipPlayer";
import ShotChart from "@/components/court/ShotChart";

export default function JobDetailPage() {
  const params = useParams();
  const jobId = params.id as string;
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [filterType, setFilterType] = useState<string>("");
  const [selectedClip, setSelectedClip] = useState<Highlight | null>(null);
  const [stats, setStats] = useState<Stat[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadJob = () => {
      api.jobs
        .get(jobId)
        .then((j) => setJob(j as ProcessingJob))
        .catch((err) => setError(err instanceof Error ? err.message : "Failed to load job"));
    };

    loadJob();
    // Poll while processing
    const interval = setInterval(() => {
      api.jobs.get(jobId).then((j) => {
        const updated = j as ProcessingJob;
        setJob(updated);
        if (updated.status === "completed" || updated.status === "failed") {
          clearInterval(interval);
        }
      }).catch(() => {});
    }, 5000);

    return () => clearInterval(interval);
  }, [jobId]);

  useEffect(() => {
    if (job?.status === "completed") {
      api.highlights
        .listByJob(jobId, filterType || undefined)
        .then((h) => setHighlights(h as Highlight[]))
        .catch(() => {});
      api.stats
        .listByJob(jobId)
        .then((s) => setStats(s as Stat[]))
        .catch(() => {});
    }
  }, [jobId, job?.status, filterType]);

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

  if (!job) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  const statusColors: Record<string, string> = {
    pending: "bg-blue-600",
    processing: "bg-yellow-600",
    completed: "bg-green-600",
    failed: "bg-red-600",
  };

  const eventTypeLabels: Record<string, string> = {
    made_basket: "Made Basket",
    steal: "Steal",
    assist: "Assist",
    rebound: "Rebound",
  };

  return (
    <div className="max-w-5xl mx-auto p-8">
      <Link href="/dashboard" className="text-sm text-orange-400 hover:text-orange-300 mb-4 inline-block">
        &larr; Back to Dashboard
      </Link>

      <div className="flex items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold">Job Results</h1>
        <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusColors[job.status] || "bg-gray-600"}`}>
          {job.status}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
          <div className="text-sm text-gray-400">Events</div>
          <div className="text-2xl font-bold">{job.events_count ?? "—"}</div>
        </div>
        <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
          <div className="text-sm text-gray-400">Highlights</div>
          <div className="text-2xl font-bold">{job.highlights_count ?? "—"}</div>
        </div>
        <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
          <div className="text-sm text-gray-400">Started</div>
          <div className="text-sm">{job.started_at ? new Date(job.started_at).toLocaleTimeString() : "—"}</div>
        </div>
        <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
          <div className="text-sm text-gray-400">Completed</div>
          <div className="text-sm">{job.completed_at ? new Date(job.completed_at).toLocaleTimeString() : "—"}</div>
        </div>
      </div>

      {job.status === "processing" && (
        <div className="p-6 bg-gray-900 rounded-lg border border-yellow-700 text-center mb-8">
          <div className="text-yellow-400 text-lg font-medium mb-2">Processing Video...</div>
          <p className="text-gray-400 text-sm">
            The GPU worker is analyzing the video. This page will update automatically when complete.
          </p>
        </div>
      )}

      {job.status === "pending" && (
        <div className="p-6 bg-gray-900 rounded-lg border border-blue-700 text-center mb-8">
          <div className="text-blue-400 text-lg font-medium mb-2">Queued</div>
          <p className="text-gray-400 text-sm">
            Waiting for the GPU worker to pick up this job.
          </p>
        </div>
      )}

      {job.status === "failed" && job.error_message && (
        <div className="p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-300 mb-8">
          <div className="font-medium mb-1">Processing Failed</div>
          <p className="text-sm">{job.error_message}</p>
        </div>
      )}

      {/* Highlights */}
      {job.status === "completed" && (
        <div>
          <div className="flex items-center gap-4 mb-4">
            <h2 className="text-xl font-semibold">Highlights</h2>
            <div className="flex gap-2">
              <button
                onClick={() => setFilterType("")}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  !filterType ? "bg-orange-600" : "bg-gray-800 hover:bg-gray-700"
                }`}
              >
                All
              </button>
              {["made_basket", "steal", "assist", "rebound"].map((type) => (
                <button
                  key={type}
                  onClick={() => setFilterType(type)}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    filterType === type ? "bg-orange-600" : "bg-gray-800 hover:bg-gray-700"
                  }`}
                >
                  {eventTypeLabels[type] || type}
                </button>
              ))}
            </div>
          </div>

          {/* Selected clip player */}
          {selectedClip && selectedClip.file_key && (
            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-sm font-medium">
                    {eventTypeLabels[selectedClip.event_type] || selectedClip.event_type}
                  </span>
                  <span className="text-sm text-gray-400 ml-3">
                    {Math.floor(selectedClip.start_time / 60)}:{String(Math.floor(selectedClip.start_time % 60)).padStart(2, "0")}
                    {selectedClip.confidence && ` — ${Math.round(selectedClip.confidence * 100)}% confidence`}
                  </span>
                </div>
                <button onClick={() => setSelectedClip(null)} className="text-sm text-gray-400 hover:text-white">
                  Close
                </button>
              </div>
              <ClipPlayer src={api.files.getUrl(selectedClip.file_key)} autoPlay />
            </div>
          )}

          {highlights.length === 0 ? (
            <p className="text-gray-500">No highlights found for this filter.</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {highlights.map((h) => (
                <button
                  key={h.id}
                  onClick={() => setSelectedClip(h)}
                  className={`text-left rounded-lg overflow-hidden transition-all ${
                    selectedClip?.id === h.id
                      ? "ring-2 ring-orange-500"
                      : "hover:ring-1 hover:ring-gray-600"
                  }`}
                >
                  {h.thumbnail_file_key ? (
                    <img
                      src={api.files.getUrl(h.thumbnail_file_key)}
                      alt={h.event_type}
                      className="w-full aspect-video object-cover bg-gray-800"
                    />
                  ) : (
                    <div className="w-full aspect-video bg-gray-800 flex items-center justify-center text-gray-500 text-xs">
                      No thumbnail
                    </div>
                  )}
                  <div className="p-2 bg-gray-900">
                    <div className="text-xs font-medium">{eventTypeLabels[h.event_type] || h.event_type}</div>
                    <div className="text-xs text-gray-400">
                      {Math.floor(h.start_time / 60)}:{String(Math.floor(h.start_time % 60)).padStart(2, "0")}
                      {h.confidence && ` — ${Math.round(h.confidence * 100)}%`}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Shot Chart */}
          {(() => {
            const courtShots = stats
              .filter((s) => s.court_x !== null && s.court_y !== null)
              .map((s) => ({
                court_x: s.court_x!,
                court_y: s.court_y!,
                made: s.event_type === "made_basket",
                event_type: s.event_type,
              }));
            if (courtShots.length === 0) return null;
            return (
              <div className="mt-8">
                <h2 className="text-xl font-semibold mb-4">Shot Chart</h2>
                <div className="bg-gray-900 rounded-lg border border-gray-700 p-4 inline-block">
                  <ShotChart shots={courtShots} />
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
