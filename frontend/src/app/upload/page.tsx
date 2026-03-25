"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Roster } from "@/types";

type Step = "game-info" | "rosters" | "video";

interface PlayerEntry {
  name: string;
  jersey_number: string;
  height_inches: string;
  position: string;
}

export default function UploadPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("game-info");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Step 1: Game info
  const [title, setTitle] = useState("");
  const [homeTeam, setHomeTeam] = useState("");
  const [awayTeam, setAwayTeam] = useState("");
  const [gameDate, setGameDate] = useState("");

  // Step 2: Rosters
  const [existingRosters, setExistingRosters] = useState<Roster[]>([]);
  const [homeRosterId, setHomeRosterId] = useState<string>("");
  const [awayRosterId, setAwayRosterId] = useState<string>("");
  const [showNewRoster, setShowNewRoster] = useState<"home" | "away" | null>(null);
  const [newRosterColor, setNewRosterColor] = useState("#FFFFFF");
  const [newRosterPlayers, setNewRosterPlayers] = useState<PlayerEntry[]>([
    { name: "", jersey_number: "", height_inches: "", position: "" },
  ]);
  const [teamPhoto, setTeamPhoto] = useState<File | null>(null);

  useEffect(() => {
    api.rosters.list("default").then((r) => setExistingRosters(r as Roster[])).catch(() => {});
  }, []);

  const addPlayerRow = () => {
    setNewRosterPlayers([...newRosterPlayers, { name: "", jersey_number: "", height_inches: "", position: "" }]);
  };

  const updatePlayerRow = (idx: number, field: keyof PlayerEntry, value: string) => {
    const updated = [...newRosterPlayers];
    updated[idx] = { ...updated[idx], [field]: value };
    setNewRosterPlayers(updated);
  };

  const createNewRoster = async (teamName: string, side: "home" | "away") => {
    setError(null);
    try {
      const players = newRosterPlayers
        .filter((p) => p.name && p.jersey_number)
        .map((p) => ({
          name: p.name,
          jersey_number: parseInt(p.jersey_number),
          height_inches: p.height_inches ? parseInt(p.height_inches) : undefined,
          position: p.position || undefined,
        }));

      const roster = (await api.rosters.create({
        team_name: teamName,
        jersey_color_primary: newRosterColor,
        user_id: "default",
        players,
      })) as Roster;

      // Upload team photo if provided
      if (teamPhoto) {
        await api.rosters.uploadTeamPhoto(roster.id, teamPhoto);
      }

      if (side === "home") setHomeRosterId(roster.id);
      else setAwayRosterId(roster.id);

      setExistingRosters([roster, ...existingRosters]);
      setShowNewRoster(null);
      setNewRosterPlayers([{ name: "", jersey_number: "", height_inches: "", position: "" }]);
      setTeamPhoto(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create roster");
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

    try {
      const game = (await api.games.create({
        title,
        home_team: homeTeam,
        away_team: awayTeam,
        game_date: new Date(gameDate).toISOString(),
        user_id: "default",
        home_roster_id: homeRosterId || undefined,
        away_roster_id: awayRosterId || undefined,
      })) as { id: string };

      await api.uploads.uploadVideo(game.id, videoFile, setProgress);
      await api.uploads.triggerProcessing(game.id);

      router.push(`/games/${game.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-2">Upload Game Film</h1>
      <div className="flex gap-2 mb-8">
        {(["game-info", "rosters", "video"] as Step[]).map((s, i) => (
          <div
            key={s}
            className={`flex-1 h-1 rounded ${step === s ? "bg-orange-600" : i < ["game-info", "rosters", "video"].indexOf(step) ? "bg-orange-800" : "bg-gray-700"}`}
          />
        ))}
      </div>

      {error && (
        <div className="p-3 mb-6 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Step 1: Game Info */}
      {step === "game-info" && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Game Details</h2>
          <div>
            <label className="block text-sm font-medium mb-2">Game Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              type="text"
              required
              placeholder="e.g. Varsity vs Lincoln - Jan 15"
              className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">Home Team</label>
              <input
                value={homeTeam}
                onChange={(e) => setHomeTeam(e.target.value)}
                type="text"
                required
                className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Away Team</label>
              <input
                value={awayTeam}
                onChange={(e) => setAwayTeam(e.target.value)}
                type="text"
                required
                className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Game Date</label>
            <input
              value={gameDate}
              onChange={(e) => setGameDate(e.target.value)}
              type="date"
              required
              className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
            />
          </div>
          <button
            onClick={() => setStep("rosters")}
            disabled={!title || !homeTeam || !awayTeam || !gameDate}
            className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
          >
            Next: Team Rosters
          </button>
        </div>
      )}

      {/* Step 2: Rosters (optional) */}
      {step === "rosters" && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Team Rosters</h2>
          <p className="text-gray-400 text-sm">
            Optional — adding rosters with player photos dramatically improves player identification accuracy.
          </p>

          {/* Home Roster */}
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
            <h3 className="font-medium mb-3">{homeTeam || "Home"} Roster</h3>
            {existingRosters.length > 0 && (
              <select
                value={homeRosterId}
                onChange={(e) => setHomeRosterId(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 rounded-lg border border-gray-600 mb-3"
              >
                <option value="">Select existing roster...</option>
                {existingRosters.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.team_name} {r.season ? `(${r.season})` : ""} — {r.players.length} players
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={() => setShowNewRoster(showNewRoster === "home" ? null : "home")}
              className="text-sm text-orange-400 hover:text-orange-300"
            >
              {showNewRoster === "home" ? "Cancel" : "+ Create new roster"}
            </button>
          </div>

          {/* Away Roster */}
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
            <h3 className="font-medium mb-3">{awayTeam || "Away"} Roster</h3>
            {existingRosters.length > 0 && (
              <select
                value={awayRosterId}
                onChange={(e) => setAwayRosterId(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 rounded-lg border border-gray-600 mb-3"
              >
                <option value="">Select existing roster...</option>
                {existingRosters.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.team_name} {r.season ? `(${r.season})` : ""} — {r.players.length} players
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={() => setShowNewRoster(showNewRoster === "away" ? null : "away")}
              className="text-sm text-orange-400 hover:text-orange-300"
            >
              {showNewRoster === "away" ? "Cancel" : "+ Create new roster"}
            </button>
          </div>

          {/* New Roster Form */}
          {showNewRoster && (
            <div className="p-4 bg-gray-800 rounded-lg border border-orange-600 space-y-4">
              <h3 className="font-medium">
                New Roster for {showNewRoster === "home" ? homeTeam : awayTeam}
              </h3>

              <div>
                <label className="block text-sm mb-1">Jersey Color</label>
                <div className="flex gap-3 items-center">
                  <input
                    type="color"
                    value={newRosterColor}
                    onChange={(e) => setNewRosterColor(e.target.value)}
                    className="w-10 h-10 rounded cursor-pointer"
                  />
                  <span className="text-sm text-gray-400">{newRosterColor}</span>
                </div>
              </div>

              <div>
                <label className="block text-sm mb-1">Team Photo (optional — auto-detects players)</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setTeamPhoto(e.target.files?.[0] || null)}
                  className="w-full text-sm file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:bg-gray-700 file:text-white"
                />
              </div>

              <div>
                <label className="block text-sm mb-2">Players</label>
                <div className="space-y-2">
                  {newRosterPlayers.map((p, i) => (
                    <div key={i} className="grid grid-cols-12 gap-2">
                      <input
                        placeholder="Name"
                        value={p.name}
                        onChange={(e) => updatePlayerRow(i, "name", e.target.value)}
                        className="col-span-4 px-2 py-1 bg-gray-900 rounded border border-gray-600 text-sm"
                      />
                      <input
                        placeholder="#"
                        value={p.jersey_number}
                        onChange={(e) => updatePlayerRow(i, "jersey_number", e.target.value)}
                        className="col-span-2 px-2 py-1 bg-gray-900 rounded border border-gray-600 text-sm"
                        type="number"
                      />
                      <input
                        placeholder="Height (in)"
                        value={p.height_inches}
                        onChange={(e) => updatePlayerRow(i, "height_inches", e.target.value)}
                        className="col-span-3 px-2 py-1 bg-gray-900 rounded border border-gray-600 text-sm"
                        type="number"
                      />
                      <select
                        value={p.position}
                        onChange={(e) => updatePlayerRow(i, "position", e.target.value)}
                        className="col-span-3 px-2 py-1 bg-gray-900 rounded border border-gray-600 text-sm"
                      >
                        <option value="">Pos</option>
                        <option value="PG">PG</option>
                        <option value="SG">SG</option>
                        <option value="SF">SF</option>
                        <option value="PF">PF</option>
                        <option value="C">C</option>
                      </select>
                    </div>
                  ))}
                </div>
                <button
                  onClick={addPlayerRow}
                  className="mt-2 text-sm text-gray-400 hover:text-white"
                >
                  + Add player
                </button>
              </div>

              <button
                onClick={() =>
                  createNewRoster(
                    showNewRoster === "home" ? homeTeam : awayTeam,
                    showNewRoster,
                  )
                }
                className="w-full py-2 bg-orange-600 hover:bg-orange-700 rounded-lg text-sm font-medium"
              >
                Save Roster
              </button>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep("game-info")}
              className="flex-1 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg font-medium transition-colors"
            >
              Back
            </button>
            <button
              onClick={() => setStep("video")}
              className="flex-1 py-3 bg-orange-600 hover:bg-orange-700 rounded-lg font-medium transition-colors"
            >
              {homeRosterId || awayRosterId ? "Next: Upload Video" : "Skip & Upload Video"}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Video Upload */}
      {step === "video" && (
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
              onClick={() => setStep("rosters")}
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
