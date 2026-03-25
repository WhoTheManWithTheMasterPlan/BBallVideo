"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Game } from "@/types";

export default function GameDetailPage() {
  const params = useParams();
  const gameId = params.id as string;
  const [game, setGame] = useState<Game | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.games
      .get(gameId)
      .then((g) => setGame(g as Game))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load game"));
  }, [gameId]);

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <div className="p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-300">
          {error}
        </div>
        <Link href="/dashboard" className="mt-4 inline-block text-orange-400 hover:text-orange-300">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  if (!game) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  const statusColors: Record<string, string> = {
    uploaded: "bg-blue-600",
    processing: "bg-yellow-600",
    completed: "bg-green-600",
    failed: "bg-red-600",
  };

  return (
    <div className="max-w-4xl mx-auto p-8">
      <Link href="/dashboard" className="text-sm text-orange-400 hover:text-orange-300 mb-4 inline-block">
        &larr; Back to Dashboard
      </Link>

      <div className="flex items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold">{game.title}</h1>
        <span
          className={`px-3 py-1 rounded-full text-xs font-medium ${statusColors[game.status] || "bg-gray-600"}`}
        >
          {game.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-6 mb-8">
        <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Home Team</div>
          <div className="text-lg font-medium">{game.home_team}</div>
        </div>
        <div className="p-4 bg-gray-900 rounded-lg border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Away Team</div>
          <div className="text-lg font-medium">{game.away_team}</div>
        </div>
      </div>

      <div className="p-4 bg-gray-900 rounded-lg border border-gray-700 mb-8">
        <div className="text-sm text-gray-400 mb-1">Game Date</div>
        <div>{new Date(game.game_date).toLocaleDateString()}</div>
      </div>

      {game.status === "processing" && (
        <div className="p-6 bg-gray-900 rounded-lg border border-yellow-700 text-center">
          <div className="text-yellow-400 text-lg font-medium mb-2">Processing Video...</div>
          <p className="text-gray-400 text-sm">
            The GPU worker will analyze the video when available. Stats and clips will appear here once complete.
          </p>
        </div>
      )}

      {game.status === "uploaded" && (
        <div className="p-6 bg-gray-900 rounded-lg border border-blue-700 text-center">
          <div className="text-blue-400 text-lg font-medium mb-2">Video Uploaded</div>
          <p className="text-gray-400 text-sm">
            Waiting for processing to begin. The video is queued and will be analyzed when the GPU worker connects.
          </p>
        </div>
      )}

      {game.status === "completed" && (
        <div className="space-y-6">
          <div className="p-6 bg-gray-900 rounded-lg border border-green-700 text-center">
            <div className="text-green-400 text-lg font-medium">Analysis Complete</div>
            <p className="text-gray-400 text-sm mt-1">Stats and clips will be displayed here.</p>
          </div>
        </div>
      )}
    </div>
  );
}
