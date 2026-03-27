"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Profile, Video, ProcessingJob, StatsSummary } from "@/types";

const USER_ID = "default";

export default function DashboardPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [videos, setVideos] = useState<Video[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [statsSummary, setStatsSummary] = useState<StatsSummary>({});

  useEffect(() => {
    api.profiles.list(USER_ID).then((p) => setProfiles(p as Profile[])).catch(() => {});
    api.videos.list(USER_ID).then((v) => setVideos(v as Video[])).catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedProfile) {
      api.jobs.listByProfile(selectedProfile.id).then((j) => setJobs(j as ProcessingJob[])).catch(() => {});
      api.stats.profileSummary(selectedProfile.id).then((s) => setStatsSummary(s as StatsSummary)).catch(() => {});
    }
  }, [selectedProfile]);

  return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <div className="flex gap-3">
          <Link
            href="/profiles/new"
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg font-medium transition-colors text-sm"
          >
            + New Profile
          </Link>
          <Link
            href="/upload"
            className="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded-lg font-medium transition-colors text-sm"
          >
            Upload Video
          </Link>
        </div>
      </div>

      {/* Profiles */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-4">Player Profiles</h2>
        {profiles.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-900 rounded-lg">
            <p className="text-lg">No profiles yet.</p>
            <p className="text-sm mt-1">Create a profile to start tracking a player.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {profiles.map((profile) => (
              <button
                key={profile.id}
                onClick={() => setSelectedProfile(profile)}
                className={`p-4 rounded-lg text-left transition-colors ${
                  selectedProfile?.id === profile.id
                    ? "bg-orange-900/50 border border-orange-600"
                    : "bg-gray-900 border border-gray-700 hover:bg-gray-800"
                }`}
              >
                <div className="flex items-center gap-3">
                  {profile.photos.length > 0 ? (
                    <img
                      src={api.files.getUrl(profile.photos[0].file_key)}
                      alt={profile.name}
                      className="w-12 h-12 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-lg">
                      {profile.name[0]}
                    </div>
                  )}
                  <div>
                    <div className="font-medium">{profile.name}</div>
                    <div className="text-xs text-gray-400">
                      {profile.photos.length} photo{profile.photos.length !== 1 ? "s" : ""}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Selected Profile Stats */}
      {selectedProfile && (
        <section className="mb-10">
          <h2 className="text-xl font-semibold mb-4">{selectedProfile.name} — Stats</h2>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-700 text-center">
              <div className="text-3xl font-bold text-green-400">{statsSummary["made_basket"] || 0}</div>
              <div className="text-sm text-gray-400 mt-1">Made Baskets</div>
            </div>
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-700 text-center">
              <div className="text-3xl font-bold text-blue-400">{statsSummary["assist"] || 0}</div>
              <div className="text-sm text-gray-400 mt-1">Assists</div>
            </div>
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-700 text-center">
              <div className="text-3xl font-bold text-yellow-400">{statsSummary["steal"] || 0}</div>
              <div className="text-sm text-gray-400 mt-1">Steals</div>
            </div>
          </div>

          {/* Jobs for this profile */}
          <h3 className="text-lg font-medium mb-3">Processing Jobs</h3>
          {jobs.length === 0 ? (
            <p className="text-gray-500 text-sm">No videos processed for this profile yet.</p>
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
                    <div className="text-xs text-gray-400">
                      {new Date(job.created_at).toLocaleString()}
                    </div>
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
        </section>
      )}

      {/* Recent Videos */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Videos</h2>
        {videos.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-900 rounded-lg">
            <p className="text-lg">No videos yet.</p>
            <p className="text-sm mt-1">Upload game film to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {videos.map((video) => (
              <Link
                key={video.id}
                href={`/videos/${video.id}`}
                className="block p-4 bg-gray-900 rounded-lg border border-gray-700 hover:bg-gray-800 transition-colors"
              >
                <h3 className="font-medium">{video.title}</h3>
                {video.opponent && <p className="text-sm text-gray-400">vs {video.opponent}</p>}
                {video.game_date && (
                  <p className="text-xs text-gray-500 mt-1">
                    {new Date(video.game_date).toLocaleDateString()}
                  </p>
                )}
                <span
                  className={`inline-block mt-2 px-2 py-1 rounded text-xs ${
                    video.file_key ? "bg-green-900 text-green-300" : "bg-gray-800 text-gray-400"
                  }`}
                >
                  {video.file_key ? "Uploaded" : "No file"}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
