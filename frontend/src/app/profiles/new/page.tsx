"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Profile } from "@/types";

const USER_ID = "default";

export default function NewProfilePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [jerseyNumber, setJerseyNumber] = useState("");
  const [teamColorPrimary, setTeamColorPrimary] = useState("");
  const [teamColorSecondary, setTeamColorSecondary] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setError(null);
    setCreating(true);

    try {
      const profile = (await api.profiles.create({
        name: name.trim(),
        user_id: USER_ID,
        jersey_number: jerseyNumber ? parseInt(jerseyNumber) : undefined,
        team_color_primary: teamColorPrimary || undefined,
        team_color_secondary: teamColorSecondary || undefined,
      })) as Profile;

      if (photos.length > 0) {
        setUploadingPhotos(true);
        for (const photo of photos) {
          await api.profiles.uploadPhoto(profile.id, photo);
        }
      }

      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create profile");
      setCreating(false);
      setUploadingPhotos(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto p-8">
      <h1 className="text-3xl font-bold mb-6">Create Player Profile</h1>

      {error && (
        <div className="p-3 mb-6 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-6">
        <div>
          <label className="block text-sm font-medium mb-2">Player Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            type="text"
            required
            placeholder="e.g. Tyler Smith"
            className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Jersey Number</label>
          <input
            value={jerseyNumber}
            onChange={(e) => setJerseyNumber(e.target.value)}
            type="number"
            min="0"
            max="99"
            placeholder="e.g. 23"
            className="w-32 px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none"
          />
          <p className="text-gray-500 text-xs mt-1">Helps the AI confirm player identity via jersey OCR.</p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Team Jersey Colors</label>
          <p className="text-gray-500 text-xs mb-3">
            Describe the jersey colors so the AI can classify teams (e.g. "white", "dark blue", "red and black").
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Primary color</label>
              <input
                value={teamColorPrimary}
                onChange={(e) => setTeamColorPrimary(e.target.value)}
                type="text"
                placeholder="e.g. white"
                className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Secondary color (optional)</label>
              <input
                value={teamColorSecondary}
                onChange={(e) => setTeamColorSecondary(e.target.value)}
                type="text"
                placeholder="e.g. blue"
                className="w-full px-4 py-2 bg-gray-900 rounded-lg border border-gray-700 focus:border-orange-500 focus:outline-none text-sm"
              />
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Player Photos</label>
          <p className="text-gray-400 text-xs mb-3">
            Upload clear photos of the player. These are used for AI identification in game footage.
            More photos = better accuracy.
          </p>
          <label className="inline-block px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm cursor-pointer transition-colors">
            + Add Photos
            <input
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                const newFiles = Array.from(e.target.files || []);
                if (newFiles.length > 0) setPhotos((prev) => [...prev, ...newFiles]);
                e.target.value = "";
              }}
            />
          </label>
          {photos.length > 0 && (
            <div className="mt-3 space-y-2">
              {photos.map((file, i) => (
                <div key={i} className="flex items-center justify-between p-2 bg-gray-900 rounded-lg border border-gray-700 text-sm">
                  <span className="text-gray-300 truncate mr-3">{file.name}</span>
                  <button
                    type="button"
                    onClick={() => setPhotos((prev) => prev.filter((_, j) => j !== i))}
                    className="text-red-400 hover:text-red-300 text-xs shrink-0"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={handleSubmit}
          disabled={!name.trim() || creating}
          className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
        >
          {uploadingPhotos ? "Uploading photos..." : creating ? "Creating..." : "Create Profile"}
        </button>
      </div>
    </div>
  );
}
