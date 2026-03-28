"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Profile, Team, TeamPhoto } from "@/types";

export default function ProfileDetailPage() {
  const params = useParams();
  const profileId = params.id as string;

  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Team form
  const [showTeamForm, setShowTeamForm] = useState(false);
  const [editingTeam, setEditingTeam] = useState<Team | null>(null);
  const [teamName, setTeamName] = useState("");
  const [teamJersey, setTeamJersey] = useState("");
  const [teamColorPrimary, setTeamColorPrimary] = useState("");
  const [teamColorSecondary, setTeamColorSecondary] = useState("");
  const [savingTeam, setSavingTeam] = useState(false);
  const [deletingTeam, setDeletingTeam] = useState<string | null>(null);

  // Photo management
  const [uploadingPhotoTeamId, setUploadingPhotoTeamId] = useState<string | null>(null);
  const [deletingPhoto, setDeletingPhoto] = useState<string | null>(null);

  // Expanded team
  const [expandedTeamId, setExpandedTeamId] = useState<string | null>(null);

  const loadProfile = () => {
    api.profiles.get(profileId).then((p) => setProfile(p as Profile)).catch(() => {});
  };

  useEffect(() => {
    loadProfile();
  }, [profileId]);

  const openTeamForm = (team?: Team) => {
    if (team) {
      setEditingTeam(team);
      setTeamName(team.name);
      setTeamJersey(team.jersey_number !== null ? String(team.jersey_number) : "");
      setTeamColorPrimary(team.color_primary || "");
      setTeamColorSecondary(team.color_secondary || "");
    } else {
      setEditingTeam(null);
      setTeamName("");
      setTeamJersey("");
      setTeamColorPrimary("");
      setTeamColorSecondary("");
    }
    setShowTeamForm(true);
  };

  const handleSaveTeam = async () => {
    if (!teamName.trim()) return;
    setError(null);
    setSavingTeam(true);

    try {
      const data = {
        name: teamName.trim(),
        jersey_number: teamJersey ? parseInt(teamJersey) : undefined,
        color_primary: teamColorPrimary || undefined,
        color_secondary: teamColorSecondary || undefined,
      };

      if (editingTeam) {
        await api.teams.update(profileId, editingTeam.id, data);
      } else {
        await api.teams.create(profileId, data);
      }
      setShowTeamForm(false);
      loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save team");
    } finally {
      setSavingTeam(false);
    }
  };

  const handleDeleteTeam = async (teamId: string) => {
    setDeletingTeam(teamId);
    setError(null);
    try {
      await api.teams.delete(profileId, teamId);
      if (expandedTeamId === teamId) setExpandedTeamId(null);
      loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete team");
    } finally {
      setDeletingTeam(null);
    }
  };

  const handleAddPhotos = async (teamId: string, files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    setUploadingPhotoTeamId(teamId);
    try {
      for (const file of Array.from(files)) {
        await api.teams.uploadPhoto(profileId, teamId, file);
      }
      loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload photo");
    } finally {
      setUploadingPhotoTeamId(null);
    }
  };

  const handleDeletePhoto = async (teamId: string, photoId: string) => {
    setDeletingPhoto(photoId);
    setError(null);
    try {
      await api.teams.deletePhoto(profileId, teamId, photoId);
      loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete photo");
    } finally {
      setDeletingPhoto(null);
    }
  };

  if (!profile) {
    return <div className="max-w-2xl mx-auto p-8 text-gray-400">Loading...</div>;
  }

  const teams = profile.teams || [];

  return (
    <div className="max-w-2xl mx-auto p-8">
      <Link href="/dashboard" className="text-sm text-gray-400 hover:text-white mb-4 inline-block">
        &larr; Back to Dashboard
      </Link>

      <h1 className="text-3xl font-bold mb-8">{profile.name}</h1>

      {error && (
        <div className="p-3 mb-6 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Teams Section */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Teams ({teams.length})</h2>
          <button
            onClick={() => openTeamForm()}
            className="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded-lg font-medium text-sm transition-colors"
          >
            + Add Team
          </button>
        </div>

        <p className="text-gray-400 text-xs mb-4">
          Each team has its own jersey number, colors, and photos for AI identification.
        </p>

        {/* Team Form */}
        {showTeamForm && (
          <div className="p-4 mb-4 bg-gray-900 rounded-lg border border-gray-700 space-y-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Team Name</label>
              <input
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                type="text"
                placeholder="e.g. Lincoln Varsity"
                className="w-full px-3 py-2 bg-gray-800 rounded border border-gray-600 focus:border-orange-500 focus:outline-none text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Jersey Number</label>
              <input
                value={teamJersey}
                onChange={(e) => setTeamJersey(e.target.value)}
                type="number"
                min="0"
                max="99"
                placeholder="e.g. 23"
                className="w-32 px-3 py-2 bg-gray-800 rounded border border-gray-600 focus:border-orange-500 focus:outline-none text-sm"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Primary Jersey Color</label>
                <input
                  value={teamColorPrimary}
                  onChange={(e) => setTeamColorPrimary(e.target.value)}
                  type="text"
                  placeholder="e.g. white"
                  className="w-full px-3 py-2 bg-gray-800 rounded border border-gray-600 focus:border-orange-500 focus:outline-none text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Secondary Color (optional)</label>
                <input
                  value={teamColorSecondary}
                  onChange={(e) => setTeamColorSecondary(e.target.value)}
                  type="text"
                  placeholder="e.g. blue"
                  className="w-full px-3 py-2 bg-gray-800 rounded border border-gray-600 focus:border-orange-500 focus:outline-none text-sm"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleSaveTeam}
                disabled={!teamName.trim() || savingTeam}
                className="px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-700 rounded text-sm font-medium transition-colors"
              >
                {savingTeam ? "Saving..." : editingTeam ? "Update Team" : "Add Team"}
              </button>
              <button
                onClick={() => setShowTeamForm(false)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Team List */}
        {teams.length === 0 && !showTeamForm ? (
          <div className="text-center py-8 text-gray-500 bg-gray-900 rounded-lg border border-gray-700">
            <p>No teams yet.</p>
            <p className="text-sm mt-1">Add a team with jersey number, colors, and photos.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {teams.map((team) => {
              const isExpanded = expandedTeamId === team.id;
              const teamPhotos: TeamPhoto[] = team.photos || [];
              return (
                <div key={team.id} className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
                  {/* Team Header */}
                  <button
                    onClick={() => setExpandedTeamId(isExpanded ? null : team.id)}
                    className="w-full flex items-center justify-between p-4 text-left hover:bg-gray-800 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      {teamPhotos.length > 0 ? (
                        <img
                          src={api.files.getUrl(teamPhotos[0].file_key)}
                          alt={team.name}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-sm">
                          {team.name[0]}
                        </div>
                      )}
                      <div>
                        <div className="font-medium text-sm">
                          {team.name}
                          {team.jersey_number !== null && (
                            <span className="ml-2 text-gray-400">#{team.jersey_number}</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400">
                          {team.color_primary || "No colors"}
                          {team.color_secondary && ` / ${team.color_secondary}`}
                          {" · "}
                          {teamPhotos.length} photo{teamPhotos.length !== 1 ? "s" : ""}
                        </div>
                      </div>
                    </div>
                    <span className="text-gray-500 text-xs">{isExpanded ? "▲" : "▼"}</span>
                  </button>

                  {/* Expanded Team Detail */}
                  {isExpanded && (
                    <div className="px-4 pb-4 border-t border-gray-700 pt-3 space-y-4">
                      {/* Actions */}
                      <div className="flex gap-2">
                        <button
                          onClick={() => openTeamForm(team)}
                          className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs transition-colors"
                        >
                          Edit Team
                        </button>
                        <button
                          onClick={() => handleDeleteTeam(team.id)}
                          disabled={deletingTeam === team.id}
                          className="px-3 py-1 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded text-xs transition-colors"
                        >
                          {deletingTeam === team.id ? "Deleting..." : "Delete Team"}
                        </button>
                      </div>

                      {/* Photos */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium">Photos ({teamPhotos.length})</span>
                          <label className="px-3 py-1 bg-orange-600 hover:bg-orange-700 rounded text-xs font-medium cursor-pointer transition-colors">
                            {uploadingPhotoTeamId === team.id ? "Uploading..." : "+ Add Photos"}
                            <input
                              type="file"
                              accept="image/*"
                              multiple
                              className="hidden"
                              disabled={uploadingPhotoTeamId === team.id}
                              onChange={(e) => {
                                handleAddPhotos(team.id, e.target.files);
                                e.target.value = "";
                              }}
                            />
                          </label>
                        </div>

                        <p className="text-gray-400 text-xs mb-3">
                          Upload photos of the player in this team&apos;s uniform. More photos = better AI identification.
                        </p>

                        {teamPhotos.length === 0 ? (
                          <div className="text-center py-6 text-gray-500 bg-gray-800 rounded-lg text-sm">
                            No photos yet. Upload photos in this team&apos;s jersey.
                          </div>
                        ) : (
                          <div className="grid grid-cols-3 gap-3">
                            {teamPhotos.map((photo) => (
                              <div key={photo.id} className="relative group">
                                <img
                                  src={api.files.getUrl(photo.file_key)}
                                  alt="Player photo"
                                  className="w-full aspect-square object-cover rounded-lg border border-gray-700"
                                />
                                <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/80 to-transparent rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity">
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs text-gray-300">
                                      {photo.has_embedding ? "Embedded" : "No embedding"}
                                    </span>
                                    <button
                                      onClick={() => handleDeletePhoto(team.id, photo.id)}
                                      disabled={deletingPhoto === photo.id}
                                      className="px-2 py-1 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded text-xs transition-colors"
                                    >
                                      {deletingPhoto === photo.id ? "..." : "Delete"}
                                    </button>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
