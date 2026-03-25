"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Game {
  id: string;
  title: string;
  home_team: string;
  away_team: string;
  game_date: string;
  status: string;
}

export default function DashboardPage() {
  const [games, setGames] = useState<Game[]>([]);

  useEffect(() => {
    // TODO: Fetch games from API
  }, []);

  return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">Games</h1>
        <Link
          href="/upload"
          className="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded-lg font-medium transition-colors"
        >
          Upload New Game
        </Link>
      </div>

      {games.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <p className="text-lg">No games yet.</p>
          <p>Upload your first game to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {games.map((game) => (
            <Link
              key={game.id}
              href={`/games/${game.id}`}
              className="block p-6 bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors"
            >
              <h2 className="text-lg font-semibold">{game.title}</h2>
              <p className="text-gray-400">
                {game.home_team} vs {game.away_team}
              </p>
              <p className="text-sm text-gray-500 mt-2">
                {new Date(game.game_date).toLocaleDateString()}
              </p>
              <span
                className={`inline-block mt-2 px-2 py-1 rounded text-xs ${
                  game.status === "completed"
                    ? "bg-green-900 text-green-300"
                    : game.status === "processing"
                    ? "bg-yellow-900 text-yellow-300"
                    : "bg-gray-800 text-gray-400"
                }`}
              >
                {game.status}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
