"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Profile, Team } from "@/types";

const USER_ID = "default";

type Step = "video-info" | "profile" | "team" | "upload";

export default function UploadPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("video-info");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Step 1: Video info
  const [title, setTitle] = useState("");
  const [opponent, setOpponent] = useState("");
  const [gameDate, setGameDate] = useState("");

  // Step 2: Profile selection
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");

  // Step 3: Team selection
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");

  const selectedProfile = profiles.find((p) => p.id === selectedProfileId);
  const profileTeams = selectedProfile?.teams || [];

  useEffect(() => {
    api.profiles.list(USER_ID).then((p) => setProfiles(p as Profile[])).catch(() => {});
  }, []);

  const handleProfileNext = () => {
    if (profileTeams.length > 0) {
      setStep("team");
    } else {
      setStep("upload");
    }
  };

  const handleSubmit = async () => {
    setError(null);
    setUploading(true);
    setProgress(0);

    const videoInput = document.querySelector<HTMLInputElement>('input[name="video"]');
    const videoFile = videoInput?.files?.[0];
    if (!videoFile) {
      setError("Please select a video file");
      setUploading(false);
      return;
    }

    if (!selectedProfileId) {
      setError("Please select a player profile");
      setUploading(false);
      return;
    }

    try {
      // Create video record
      const video = (await api.videos.create({
        title,
        opponent: opponent || undefined,
        game_date: gameDate ? new Date(gameDate).toISOString() : undefined,
        user_id: USER_ID,
      })) as { id: string };

      // Upload video file
      await api.videos.uploadFile(video.id, videoFile, setProgress);

      // Trigger processing with selected profile + team
      const job = (await api.videos.triggerProcessing(
        video.id,
        selectedProfileId,
        selectedTeamId || undefined,
      )) as { id: string };

      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
    }
  };

  const steps: Step[] = profileTeams.length > 0
    ? ["video-info", "profile", "team", "upload"]
    : ["video-info", "profile", "upload"];

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-2">Upload Game Film</h1>
      <div className="flex gap-2 mb-8">
        {steps.map((s, i) => (
          <div
            key={s}
            className={`flex-1 h-1 rounded ${
              step === s
                ? "bg-orange-600"
                : i < steps.indexOf(step)
                ? "bg-orange-800"
                : "bg-gray-700"
            }`}
          />
        ))}
      </div>

      {error && (
        <div className="p-3 mb-6 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Step 1: Video Info */}
      {step === "video-info" && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Video Details</h2>
          <div>
            <label className="block text-sm font-medium mb-2">Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              type="text"
              required
              placeholder="e.g. Varsity vs Lincoln - Jan 15"
              className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Opponent (optional)</label>
            <input
              value={opponent}
              onChange={(e) => setOpponent(e.target.value)}
              type="text"
              placeholder="e.g. Lincoln High"
              className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Game Date (optional)</label>
            <input
              value={gameDate}
              onChange={(e) => setGameDate(e.target.value)}
              type="date"
              className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
            />
          </div>
          <button
            onClick={() => setStep("profile")}
            disabled={!title}
            className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
          >
            Next: Select Player
          </button>
        </div>
      )}

      {/* Step 2: Profile Selection */}
      {step === "profile" && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Select Player Profile</h2>
          <p className="text-gray-400 text-sm">
            Choose which player to track in this video. The AI will identify them using their profile photos.
          </p>

          {profiles.length === 0 ? (
            <div className="p-6 bg-gray-900 rounded-lg border border-gray-700 text-center">
              <p className="text-gray-400 mb-3">No profiles yet. Create one first.</p>
              <a
                href="/profiles/new"
                className="inline-block px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded-lg text-sm font-medium transition-colors"
              >
                Create Profile
              </a>
            </div>
          ) : (
            <div className="space-y-3">
              {profiles.map((profile) => (
                <button
                  key={profile.id}
                  onClick={() => {
                    setSelectedProfileId(profile.id);
                    setSelectedTeamId("");
                  }}
                  className={`w-full flex items-center gap-4 p-4 rounded-lg text-left transition-colors ${
                    selectedProfileId === profile.id
                      ? "bg-orange-900/50 border border-orange-600"
                      : "bg-gray-900 border border-gray-700 hover:bg-gray-800"
                  }`}
                >
                  <div className="w-14 h-14 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-xl">
                    {profile.name[0]}
                  </div>
                  <div>
                    <div className="font-medium">{profile.name}</div>
                    <div className="text-xs text-gray-400">
                      {(profile.teams || []).length} team{(profile.teams || []).length !== 1 ? "s" : ""}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep("video-info")}
              className="flex-1 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg font-medium transition-colors"
            >
              Back
            </button>
            <button
              onClick={handleProfileNext}
              disabled={!selectedProfileId}
              className="flex-1 py-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
            >
              {profileTeams.length > 0 ? "Next: Select Team" : "Next: Upload Video"}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Team Selection (only if profile has teams) */}
      {step === "team" && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Select Team</h2>
          <p className="text-gray-400 text-sm">
            Which team is {selectedProfile?.name} playing for in this game?
            This tells the AI what jersey colors to look for.
          </p>

          <div className="space-y-3">
            {profileTeams.map((team) => (
              <button
                key={team.id}
                onClick={() => setSelectedTeamId(team.id)}
                className={`w-full flex items-center justify-between p-4 rounded-lg text-left transition-colors ${
                  selectedTeamId === team.id
                    ? "bg-orange-900/50 border border-orange-600"
                    : "bg-gray-900 border border-gray-700 hover:bg-gray-800"
                }`}
              >
                <div className="flex items-center gap-3">
                  {team.photos?.length > 0 ? (
                    <img
                      src={api.files.getUrl(team.photos[0].file_key)}
                      alt={team.name}
                      className="w-10 h-10 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-sm">
                      {team.name[0]}
                    </div>
                  )}
                  <div>
                    <div className="font-medium">
                      {team.name}
                      {team.jersey_number !== null && (
                        <span className="ml-2 text-sm text-gray-400">#{team.jersey_number}</span>
                      )}
                    </div>
                    <div className="text-xs text-gray-400">
                      {team.color_primary || "No colors"}
                      {team.color_secondary && ` / ${team.color_secondary}`}
                      {" · "}
                      {(team.photos || []).length} photo{(team.photos || []).length !== 1 ? "s" : ""}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => setStep("profile")}
              className="flex-1 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg font-medium transition-colors"
            >
              Back
            </button>
            <button
              onClick={() => setStep("upload")}
              disabled={!selectedTeamId}
              className="flex-1 py-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
            >
              Next: Upload Video
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Video Upload */}
      {step === "upload" && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Upload Video</h2>

          <div>
            <label className="block text-sm font-medium mb-2">Video File</label>
            <input
              name="video"
              type="file"
              accept=".mp4,.mov,.avi,.mkv"
              required
              className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:bg-orange-600 file:text-white file:cursor-pointer"
            />
            <p className="text-sm text-gray-500 mt-1">
              Supports MP4, MOV, AVI, MKV. Max 2GB.
            </p>
          </div>

          {uploading && (
            <div>
              <div className="w-full bg-gray-800 rounded-full h-2">
                <div
                  className="bg-orange-600 h-2 rounded-full transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-sm text-gray-400 mt-1">{progress}% uploaded</p>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep(profileTeams.length > 0 ? "team" : "profile")}
              disabled={uploading}
              className="flex-1 py-3 bg-gray-800 hover:bg-gray-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
            >
              Back
            </button>
            <button
              onClick={handleSubmit}
              disabled={uploading}
              className="flex-1 py-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
            >
              {uploading ? "Uploading..." : "Upload & Analyze"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
