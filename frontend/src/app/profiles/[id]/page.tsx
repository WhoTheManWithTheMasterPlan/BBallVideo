"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Profile, ProfilePhoto } from "@/types";

export default function ProfileDetailPage() {
  const params = useParams();
  const router = useRouter();
  const profileId = params.id as string;

  const [profile, setProfile] = useState<Profile | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = () => {
    api.profiles.get(profileId).then((p) => setProfile(p as Profile)).catch(() => {});
  };

  useEffect(() => {
    loadProfile();
  }, [profileId]);

  const handleAddPhotos = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    setUploading(true);

    try {
      for (const file of Array.from(files)) {
        await api.profiles.uploadPhoto(profileId, file);
      }
      loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload photo");
    } finally {
      setUploading(false);
    }
  };

  const handleDeletePhoto = async (photoId: string) => {
    setDeleting(photoId);
    setError(null);

    try {
      await api.profiles.deletePhoto(profileId, photoId);
      loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete photo");
    } finally {
      setDeleting(null);
    }
  };

  if (!profile) {
    return <div className="max-w-2xl mx-auto p-8 text-gray-400">Loading...</div>;
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      <Link href="/dashboard" className="text-sm text-gray-400 hover:text-white mb-4 inline-block">
        &larr; Back to Dashboard
      </Link>

      <div className="flex items-center gap-4 mb-8">
        {profile.photos.length > 0 ? (
          <img
            src={api.files.getUrl(profile.photos[0].file_key)}
            alt={profile.name}
            className="w-16 h-16 rounded-full object-cover"
          />
        ) : (
          <div className="w-16 h-16 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-2xl">
            {profile.name[0]}
          </div>
        )}
        <div>
          <h1 className="text-3xl font-bold">
            {profile.name}
            {profile.jersey_number !== null && (
              <span className="ml-2 text-xl text-gray-400">#{profile.jersey_number}</span>
            )}
          </h1>
          {profile.team_color_primary && (
            <p className="text-sm text-gray-400">
              {profile.team_color_primary}
              {profile.team_color_secondary && ` / ${profile.team_color_secondary}`}
            </p>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 mb-6 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Photos Section */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">
            Photos ({profile.photos.length})
          </h2>
          <label className="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded-lg font-medium text-sm cursor-pointer transition-colors">
            {uploading ? "Uploading..." : "+ Add Photos"}
            <input
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              disabled={uploading}
              onChange={(e) => handleAddPhotos(e.target.files)}
            />
          </label>
        </div>

        <p className="text-gray-400 text-xs mb-4">
          More photos from different angles and lighting = better AI identification.
          The AI uses these to match your player in game footage.
        </p>

        {profile.photos.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-900 rounded-lg border border-gray-700">
            <p>No photos yet.</p>
            <p className="text-sm mt-1">Upload photos so the AI can identify this player.</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {profile.photos.map((photo: ProfilePhoto) => (
              <div key={photo.id} className="relative group">
                <img
                  src={api.files.getUrl(photo.file_key)}
                  alt={`${profile.name} photo`}
                  className="w-full aspect-square object-cover rounded-lg border border-gray-700"
                />
                <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/80 to-transparent rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-300">
                      {photo.has_embedding ? "Embedded" : "No embedding"}
                    </span>
                    <button
                      onClick={() => handleDeletePhoto(photo.id)}
                      disabled={deleting === photo.id}
                      className="px-2 py-1 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded text-xs transition-colors"
                    >
                      {deleting === photo.id ? "..." : "Delete"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
