"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Profile } from "@/types";

const USER_ID = "default";

export default function NewProfilePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setError(null);
    setCreating(true);

    try {
      const profile = (await api.profiles.create({ name: name.trim(), user_id: USER_ID })) as Profile;

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
          <label className="block text-sm font-medium mb-2">Player Photos</label>
          <p className="text-gray-400 text-xs mb-3">
            Upload clear photos of the player. These are used for AI identification in game footage.
            More photos = better accuracy.
          </p>
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={(e) => setPhotos(Array.from(e.target.files || []))}
            className="w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:bg-gray-700 file:text-white file:cursor-pointer"
          />
          {photos.length > 0 && (
            <p className="text-sm text-gray-400 mt-2">{photos.length} photo{photos.length !== 1 ? "s" : ""} selected</p>
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
