"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { trackEvent } from "@/lib/activity";
import type { ProcessingJob, Highlight, Stat, Video, ReelResponse } from "@/types";
import ClipPlayer from "@/components/video/ClipPlayer";
import ShotChart from "@/components/court/ShotChart";

const REJECT_REASONS = [
  "Wrong player",
  "Wrong event type",
  "Nothing happened",
  "Duplicate clip",
  "Wrong team scoring",
  "Poor quality",
];

export default function JobDetailPage() {
  const params = useParams();
  const jobId = params.id as string;
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [filterType, setFilterType] = useState<string>("");
  const [filterReview, setFilterReview] = useState<string>("");
  const [selectedClip, setSelectedClip] = useState<Highlight | null>(null);
  const [stats, setStats] = useState<Stat[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [rejectReason, setRejectReason] = useState<string>("");
  const [showAddClip, setShowAddClip] = useState(false);
  const [addClipType, setAddClipType] = useState("made_basket");
  const [addClipStartMin, setAddClipStartMin] = useState("");
  const [addClipStartSec, setAddClipStartSec] = useState("");
  const [addClipEndMin, setAddClipEndMin] = useState("");
  const [addClipEndSec, setAddClipEndSec] = useState("");
  const [addClipSubmitting, setAddClipSubmitting] = useState(false);
  const [videoFileKey, setVideoFileKey] = useState<string | null>(null);
  const rawVideoRef = useRef<HTMLVideoElement>(null);
  const [reelMode, setReelMode] = useState(false);
  const [reelSelection, setReelSelection] = useState<string[]>([]);
  const [reelBuilding, setReelBuilding] = useState(false);
  const [reelResult, setReelResult] = useState<ReelResponse | null>(null);

  useEffect(() => {
    trackEvent("page_view", { jobId });
    const loadJob = () => {
      api.jobs
        .get(jobId)
        .then((j) => setJob(j as ProcessingJob))
        .catch((err) => setError(err instanceof Error ? err.message : "Failed to load job"));
    };

    loadJob();
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

  // Fetch video file_key when job loads
  useEffect(() => {
    if (job?.video_id) {
      api.videos.get(job.video_id).then((v) => {
        const video = v as Video;
        if (video.file_key) setVideoFileKey(video.file_key);
      }).catch(() => {});
    }
  }, [job?.video_id]);

  useEffect(() => {
    if (job?.status === "completed") {
      api.highlights
        .listByJob(jobId, filterType || undefined, filterReview || undefined)
        .then((h) => setHighlights(h as Highlight[]))
        .catch(() => {});
      api.stats
        .listByJob(jobId)
        .then((s) => setStats(s as Stat[]))
        .catch(() => {});
    }
  }, [jobId, job?.status, filterType, filterReview]);

  // Reset reject reason when selecting a new clip
  useEffect(() => {
    setRejectReason(selectedClip?.reject_reason || "");
  }, [selectedClip?.id]);

  const handleReview = async (highlightId: string, status: "confirmed" | "rejected", correctedType?: string | null, reason?: string | null) => {
    trackEvent("review", { highlightId, status, correctedType });
    setReviewing(true);
    try {
      const updated = await api.highlights.review(highlightId, {
        review_status: status,
        corrected_event_type: correctedType,
        reject_reason: status === "rejected" ? reason : null,
      }) as Highlight;
      setHighlights((prev) => prev.map((h) => (h.id === highlightId ? updated : h)));
      if (selectedClip?.id === highlightId) setSelectedClip(updated);
    } catch (e) {
      console.error("Review failed:", e);
    } finally {
      setReviewing(false);
    }
  };

  const handleReviewAll = async (status: "confirmed" | "rejected") => {
    trackEvent("bulk_review", { jobId, status });
    setReviewing(true);
    try {
      await api.highlights.reviewAll(jobId, status);
      const h = await api.highlights.listByJob(jobId, filterType || undefined, filterReview || undefined);
      setHighlights(h as Highlight[]);
    } catch (e) {
      console.error("Bulk review failed:", e);
    } finally {
      setReviewing(false);
    }
  };

  const refreshHighlights = async () => {
    const h = await api.highlights.listByJob(jobId, filterType || undefined, filterReview || undefined);
    setHighlights(h as Highlight[]);
    const s = await api.stats.listByJob(jobId);
    setStats(s as Stat[]);
  };

  const handleAddClip = async () => {
    const startTime = (parseInt(addClipStartMin) || 0) * 60 + (parseInt(addClipStartSec) || 0);
    const endTime = (parseInt(addClipEndMin) || 0) * 60 + (parseInt(addClipEndSec) || 0);
    if (endTime <= startTime) return;

    setAddClipSubmitting(true);
    try {
      await api.highlights.createManual(jobId, {
        event_type: addClipType,
        start_time: startTime,
        end_time: endTime,
      });
      trackEvent("manual_clip_created", { jobId, eventType: addClipType });
      await refreshHighlights();
      setShowAddClip(false);
      setAddClipStartMin("");
      setAddClipStartSec("");
      setAddClipEndMin("");
      setAddClipEndSec("");
    } catch (e) {
      console.error("Failed to create manual clip:", e);
    } finally {
      setAddClipSubmitting(false);
    }
  };

  const setStartFromVideo = () => {
    if (rawVideoRef.current) {
      const t = rawVideoRef.current.currentTime;
      setAddClipStartMin(String(Math.floor(t / 60)));
      setAddClipStartSec(String(Math.floor(t % 60)));
    }
  };

  const setEndFromVideo = () => {
    if (rawVideoRef.current) {
      const t = rawVideoRef.current.currentTime;
      setAddClipEndMin(String(Math.floor(t / 60)));
      setAddClipEndSec(String(Math.floor(t % 60)));
    }
  };

  const toggleReelMode = () => {
    if (reelMode) {
      // Exiting reel mode — clear selection
      setReelMode(false);
      setReelSelection([]);
      setReelResult(null);
    } else {
      setReelMode(true);
      setReelSelection([]);
      setReelResult(null);
      setSelectedClip(null);
    }
  };

  const toggleReelSelection = (highlightId: string) => {
    setReelSelection((prev) => {
      if (prev.includes(highlightId)) {
        return prev.filter((id) => id !== highlightId);
      }
      return [...prev, highlightId];
    });
  };

  const handleBuildReel = async () => {
    if (reelSelection.length === 0) return;
    setReelBuilding(true);
    setReelResult(null);
    try {
      const result = await api.highlights.createReel(jobId, reelSelection) as ReelResponse;
      setReelResult(result);
    } catch (e) {
      console.error("Reel build failed:", e);
    } finally {
      setReelBuilding(false);
    }
  };

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
    missed_basket: "Missed Basket",
    steal: "Steal",
    assist: "Assist",
    rebound: "Rebound",
    block: "Block",
    hustle: "Hustle",
  };

  const eventTypes = ["made_basket", "missed_basket", "steal", "assist", "rebound", "block", "hustle"];

  const reviewCounts = {
    pending: highlights.filter((h) => h.review_status === "pending").length,
    confirmed: highlights.filter((h) => h.review_status === "confirmed").length,
    rejected: highlights.filter((h) => h.review_status === "rejected").length,
  };

  const reviewBorderColor = (status: string) => {
    if (status === "confirmed") return "border-green-500";
    if (status === "rejected") return "border-red-500";
    return "border-gray-700";
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

      {/* Stats Summary */}
      {job.status === "completed" && stats.length > 0 && (() => {
        const makes = stats.filter((s) => s.event_type === "made_basket").length;
        const misses = stats.filter((s) => s.event_type === "missed_basket").length;
        const totalShots = makes + misses;
        const fgPct = totalShots > 0 ? ((makes / totalShots) * 100).toFixed(1) : "—";
        const steals = stats.filter((s) => s.event_type === "steal").length;
        const assists = stats.filter((s) => s.event_type === "assist").length;
        const rebounds = stats.filter((s) => s.event_type === "rebound").length;

        return (
          <div className="mb-8">
            <h2 className="text-xl font-semibold mb-3">Stats Summary</h2>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
              <div className="p-3 bg-gray-900 rounded-lg border border-gray-700 text-center">
                <div className="text-2xl font-bold text-green-400">{fgPct}%</div>
                <div className="text-xs text-gray-400">FG%</div>
              </div>
              <div className="p-3 bg-gray-900 rounded-lg border border-gray-700 text-center">
                <div className="text-2xl font-bold">{makes}/{totalShots}</div>
                <div className="text-xs text-gray-400">FGM/FGA</div>
              </div>
              <div className="p-3 bg-gray-900 rounded-lg border border-gray-700 text-center">
                <div className="text-2xl font-bold">{assists}</div>
                <div className="text-xs text-gray-400">Assists</div>
              </div>
              <div className="p-3 bg-gray-900 rounded-lg border border-gray-700 text-center">
                <div className="text-2xl font-bold">{steals}</div>
                <div className="text-xs text-gray-400">Steals</div>
              </div>
              <div className="p-3 bg-gray-900 rounded-lg border border-gray-700 text-center">
                <div className="text-2xl font-bold">{rebounds}</div>
                <div className="text-xs text-gray-400">Rebounds</div>
              </div>
              <div className="p-3 bg-gray-900 rounded-lg border border-gray-700 text-center">
                <div className="text-2xl font-bold">{stats.length}</div>
                <div className="text-xs text-gray-400">Total Events</div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Highlights */}
      {job.status === "completed" && (
        <div>
          {/* Review progress + bulk actions */}
          <div className="flex items-center gap-4 mb-4 text-xs">
            <span className="text-gray-400">
              <span className="text-gray-300 font-medium">{reviewCounts.pending}</span> pending
            </span>
            <span className="text-green-400">
              <span className="font-medium">{reviewCounts.confirmed}</span> confirmed
            </span>
            <span className="text-red-400">
              <span className="font-medium">{reviewCounts.rejected}</span> rejected
            </span>
            <div className="flex-1" />
            <button
              onClick={() => handleReviewAll("confirmed")}
              disabled={reviewing || reviewCounts.pending === 0}
              className="px-3 py-1 bg-green-800 hover:bg-green-700 disabled:opacity-50 rounded text-xs font-medium transition-colors"
            >
              Confirm All Pending
            </button>
            <button
              onClick={() => handleReviewAll("rejected")}
              disabled={reviewing || reviewCounts.pending === 0}
              className="px-3 py-1 bg-red-800 hover:bg-red-700 disabled:opacity-50 rounded text-xs font-medium transition-colors"
            >
              Reject All Pending
            </button>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-4 mb-4">
            <h2 className="text-xl font-semibold">Highlights</h2>
            <button
              onClick={() => { if (!showAddClip) trackEvent("add_clip_opened", { jobId }); setShowAddClip(!showAddClip); }}
              className="px-3 py-1 rounded text-xs font-medium transition-colors bg-orange-700 hover:bg-orange-600"
            >
              {showAddClip ? "Cancel" : "+ Add Clip"}
            </button>
            <button
              onClick={toggleReelMode}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                reelMode ? "bg-purple-600 hover:bg-purple-500" : "bg-purple-800 hover:bg-purple-700"
              }`}
            >
              {reelMode ? "Exit Reel Mode" : "Build Reel"}
            </button>
            <div className="flex gap-2">
              <button
                onClick={() => { trackEvent("filter_changed", { filterType: "", filterReview }); setFilterType(""); }}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  !filterType ? "bg-orange-600" : "bg-gray-800 hover:bg-gray-700"
                }`}
              >
                All
              </button>
              {["made_basket", "missed_basket", "steal", "assist", "rebound"].map((type) => (
                <button
                  key={type}
                  onClick={() => { trackEvent("filter_changed", { filterType: type, filterReview }); setFilterType(type); }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    filterType === type ? "bg-orange-600" : "bg-gray-800 hover:bg-gray-700"
                  }`}
                >
                  {eventTypeLabels[type] || type}
                </button>
              ))}
            </div>
            <div className="border-l border-gray-700 h-4" />
            <div className="flex gap-2">
              <button
                onClick={() => { trackEvent("filter_changed", { filterType, filterReview: "" }); setFilterReview(""); }}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  !filterReview ? "bg-gray-600" : "bg-gray-800 hover:bg-gray-700"
                }`}
              >
                Any Status
              </button>
              {["pending", "confirmed", "rejected"].map((rs) => (
                <button
                  key={rs}
                  onClick={() => { trackEvent("filter_changed", { filterType, filterReview: rs }); setFilterReview(rs); }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    filterReview === rs
                      ? rs === "confirmed" ? "bg-green-700" : rs === "rejected" ? "bg-red-700" : "bg-gray-600"
                      : "bg-gray-800 hover:bg-gray-700"
                  }`}
                >
                  {rs.charAt(0).toUpperCase() + rs.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Add Clip: raw video player + start/end time form */}
          {showAddClip && (
            <div className="mb-6 p-4 bg-gray-900 rounded-lg border border-orange-700">
              {/* Raw video player */}
              {videoFileKey ? (
                <div className="mb-4">
                  <div className="text-xs text-gray-400 mb-2">
                    Scrub through the video to find the missed event. Use the buttons to set start/end times from the current position.
                  </div>
                  <div className="relative rounded-lg overflow-hidden bg-black">
                    <video
                      ref={rawVideoRef}
                      src={api.files.getUrl(videoFileKey)}
                      controls
                      className="w-full aspect-video"
                    />
                  </div>
                </div>
              ) : (
                <div className="mb-4 p-4 bg-gray-800 rounded text-gray-500 text-sm text-center">
                  Raw video not available
                </div>
              )}

              {/* Controls row */}
              <div className="flex items-center gap-3 flex-wrap">
                <select
                  value={addClipType}
                  onChange={(e) => setAddClipType(e.target.value)}
                  className="bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-200"
                >
                  {eventTypes.map((type) => (
                    <option key={type} value={type}>
                      {eventTypeLabels[type] || type}
                    </option>
                  ))}
                </select>

                {/* Start time */}
                <div className="flex items-center gap-1">
                  <span className="text-xs text-gray-400">Start:</span>
                  <input
                    type="number"
                    min="0"
                    placeholder="Min"
                    value={addClipStartMin}
                    onChange={(e) => setAddClipStartMin(e.target.value)}
                    className="w-14 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-200 text-center"
                  />
                  <span className="text-gray-400">:</span>
                  <input
                    type="number"
                    min="0"
                    max="59"
                    placeholder="Sec"
                    value={addClipStartSec}
                    onChange={(e) => setAddClipStartSec(e.target.value)}
                    className="w-14 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-200 text-center"
                  />
                  <button
                    onClick={setStartFromVideo}
                    className="px-2 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300 transition-colors"
                    title="Set start from current video position"
                  >
                    Set
                  </button>
                </div>

                {/* End time */}
                <div className="flex items-center gap-1">
                  <span className="text-xs text-gray-400">End:</span>
                  <input
                    type="number"
                    min="0"
                    placeholder="Min"
                    value={addClipEndMin}
                    onChange={(e) => setAddClipEndMin(e.target.value)}
                    className="w-14 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-200 text-center"
                  />
                  <span className="text-gray-400">:</span>
                  <input
                    type="number"
                    min="0"
                    max="59"
                    placeholder="Sec"
                    value={addClipEndSec}
                    onChange={(e) => setAddClipEndSec(e.target.value)}
                    className="w-14 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-200 text-center"
                  />
                  <button
                    onClick={setEndFromVideo}
                    className="px-2 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300 transition-colors"
                    title="Set end from current video position"
                  >
                    Set
                  </button>
                </div>

                <button
                  onClick={handleAddClip}
                  disabled={addClipSubmitting || (!addClipEndMin && !addClipEndSec)}
                  className="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded text-sm font-medium transition-colors"
                >
                  {addClipSubmitting ? "Creating..." : "Create Clip"}
                </button>
                <button
                  onClick={() => setShowAddClip(false)}
                  className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Selected clip: review controls ABOVE video */}
          {selectedClip && selectedClip.file_key && (
            <div className="mb-6">
              {/* Review controls bar */}
              <div className="flex items-center gap-3 mb-3 p-3 bg-gray-900 rounded-lg border border-gray-700">
                <div className="flex items-center gap-2 mr-2">
                  <span className="text-sm font-medium">
                    {eventTypeLabels[selectedClip.corrected_event_type || selectedClip.event_type] || selectedClip.event_type}
                  </span>
                  {selectedClip.corrected_event_type && selectedClip.corrected_event_type !== selectedClip.event_type && (
                    <span className="text-xs text-yellow-400">(was: {eventTypeLabels[selectedClip.event_type]})</span>
                  )}
                  <span className="text-xs text-gray-400">
                    {Math.floor(selectedClip.start_time / 60)}:{String(Math.floor(selectedClip.start_time % 60)).padStart(2, "0")}
                    {selectedClip.confidence && ` — ${Math.round(selectedClip.confidence * 100)}%`}
                  </span>
                </div>

                <div className="flex-1" />

                {/* Correct event type */}
                <select
                  value={selectedClip.corrected_event_type || selectedClip.event_type}
                  onChange={(e) => {
                    const newType = e.target.value;
                    handleReview(selectedClip.id, "confirmed", newType !== selectedClip.event_type ? newType : null);
                  }}
                  className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                >
                  {eventTypes.map((type) => (
                    <option key={type} value={type}>
                      {eventTypeLabels[type] || type}
                    </option>
                  ))}
                </select>

                <button
                  onClick={() => handleReview(selectedClip.id, "confirmed")}
                  disabled={reviewing}
                  className={`px-4 py-1.5 rounded text-xs font-medium transition-colors ${
                    selectedClip.review_status === "confirmed"
                      ? "bg-green-600 text-white"
                      : "bg-gray-800 hover:bg-green-800 text-gray-300"
                  }`}
                >
                  Confirm
                </button>

                {/* Reject with reason */}
                <div className="flex items-center gap-1">
                  <select
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                  >
                    <option value="">Reject reason...</option>
                    {REJECT_REASONS.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => handleReview(selectedClip.id, "rejected", null, rejectReason || null)}
                    disabled={reviewing}
                    className={`px-4 py-1.5 rounded text-xs font-medium transition-colors ${
                      selectedClip.review_status === "rejected"
                        ? "bg-red-600 text-white"
                        : "bg-gray-800 hover:bg-red-800 text-gray-300"
                    }`}
                  >
                    Reject
                  </button>
                </div>

                <button onClick={() => setSelectedClip(null)} className="text-sm text-gray-400 hover:text-white ml-2">
                  Close
                </button>
              </div>

              {/* Reject reason display if already rejected */}
              {selectedClip.review_status === "rejected" && selectedClip.reject_reason && (
                <div className="text-xs text-red-400 mb-2 px-1">
                  Rejected: {selectedClip.reject_reason}
                </div>
              )}

              {/* Video player */}
              <ClipPlayer src={api.files.getUrl(selectedClip.file_key)} autoPlay />
            </div>
          )}

          {/* Reel action bar */}
          {reelMode && (
            <div className="mb-4 p-3 bg-purple-900/40 border border-purple-700 rounded-lg flex items-center gap-4">
              <span className="text-sm text-purple-200">
                <span className="font-bold">{reelSelection.length}</span>{" "}
                clip{reelSelection.length !== 1 ? "s" : ""} selected
                {reelSelection.length > 0 && " — click clips to add/remove"}
              </span>
              <div className="flex-1" />
              {reelResult && (
                <a
                  href={api.files.getUrl(reelResult.file_key)}
                  download
                  className="px-4 py-1.5 bg-green-700 hover:bg-green-600 rounded text-sm font-medium transition-colors"
                >
                  Download Reel ({reelResult.clip_count} clips, {reelResult.duration_seconds.toFixed(1)}s)
                </a>
              )}
              <button
                onClick={handleBuildReel}
                disabled={reelBuilding || reelSelection.length === 0}
                className="px-4 py-1.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded text-sm font-medium transition-colors"
              >
                {reelBuilding ? "Building..." : "Stitch Reel"}
              </button>
              <button
                onClick={toggleReelMode}
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {/* Highlight grid */}
          {highlights.length === 0 ? (
            <p className="text-gray-500">No highlights found for this filter.</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {highlights.map((h) => {
                const reelIndex = reelMode ? reelSelection.indexOf(h.id) : -1;
                const isInReel = reelIndex >= 0;
                return (
                  <button
                    key={h.id}
                    onClick={() => {
                      if (reelMode) {
                        toggleReelSelection(h.id);
                      } else {
                        trackEvent("clip_selected", { highlightId: h.id, eventType: h.event_type });
                        setSelectedClip(h);
                      }
                    }}
                    className={`relative text-left rounded-lg overflow-hidden transition-all border-2 ${
                      reelMode
                        ? isInReel
                          ? "ring-2 ring-purple-500 border-purple-500"
                          : "border-gray-700 hover:ring-1 hover:ring-purple-400"
                        : selectedClip?.id === h.id
                          ? "ring-2 ring-orange-500 " + reviewBorderColor(h.review_status)
                          : reviewBorderColor(h.review_status) + " hover:ring-1 hover:ring-gray-600"
                    }`}
                  >
                    {/* Reel selection number overlay */}
                    {reelMode && (
                      <div className={`absolute top-2 left-2 z-10 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                        isInReel
                          ? "bg-purple-600 text-white"
                          : "bg-gray-800/80 text-gray-400 border border-gray-600"
                      }`}>
                        {isInReel ? reelIndex + 1 : ""}
                      </div>
                    )}
                    {h.thumbnail_file_key ? (
                      <img
                        src={api.files.getUrl(h.thumbnail_file_key)}
                        alt={h.event_type}
                        className={`w-full aspect-video object-cover bg-gray-800 ${
                          h.review_status === "rejected" ? "opacity-40" : ""
                        }`}
                      />
                    ) : (
                      <div className="w-full aspect-video bg-gray-800 flex items-center justify-center text-gray-500 text-xs">
                        No thumbnail
                      </div>
                    )}
                    <div className="p-2 bg-gray-900">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-medium">
                          {eventTypeLabels[h.corrected_event_type || h.event_type] || h.event_type}
                        </div>
                        {h.review_status !== "pending" && (
                          <span className={`w-2 h-2 rounded-full ${
                            h.review_status === "confirmed" ? "bg-green-500" : "bg-red-500"
                          }`} />
                        )}
                      </div>
                      <div className="text-xs text-gray-400">
                        {Math.floor(h.start_time / 60)}:{String(Math.floor(h.start_time % 60)).padStart(2, "0")}
                        {h.confidence && ` — ${Math.round(h.confidence * 100)}%`}
                      </div>
                      {h.review_status === "rejected" && h.reject_reason && (
                        <div className="text-xs text-red-400 mt-0.5 truncate">{h.reject_reason}</div>
                      )}
                    </div>
                  </button>
                );
              })}
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
