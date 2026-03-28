"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Profile } from "@/types";

const USER_ID = "default";

export default function NewProfilePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setError(null);
    setCreating(true);

    try {
      const profile = (await api.profiles.create({
        name: name.trim(),
        user_id: USER_ID,
      })) as Profile;

      router.push(`/profiles/${profile.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create profile");
      setCreating(false);
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

        <button
          onClick={handleSubmit}
          disabled={!name.trim() || creating}
          className="w-full py-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
        >
          {creating ? "Creating..." : "Create Profile"}
        </button>

        <p className="text-gray-500 text-xs text-center">
          Next, you&apos;ll add teams with jersey numbers, colors, and photos.
        </p>
      </div>
    </div>
  );
}
