const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  return res.json();
}

export const api = {
  games: {
    list: (userId: string) =>
      fetchAPI(`/api/v1/games/?user_id=${userId}`),
    get: (gameId: string) =>
      fetchAPI(`/api/v1/games/${gameId}`),
    create: (data: {
      title: string;
      home_team: string;
      away_team: string;
      game_date: string;
      user_id: string;
      home_roster_id?: string;
      away_roster_id?: string;
    }) =>
      fetchAPI("/api/v1/games/", { method: "POST", body: JSON.stringify(data) }),
  },
  uploads: {
    uploadVideo: async (
      gameId: string,
      file: File,
      onProgress?: (percent: number) => void,
    ): Promise<{ file_key: string; size_mb: number }> => {
      const formData = new FormData();
      formData.append("game_id", gameId);
      formData.append("video", file);

      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API_URL}/api/v1/uploads/`);

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && onProgress) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
          }
        };

        xhr.onerror = () => reject(new Error("Upload failed"));
        xhr.send(formData);
      });
    },
    triggerProcessing: (gameId: string) =>
      fetchAPI(`/api/v1/uploads/${gameId}/process`, { method: "POST" }),
  },
  rosters: {
    list: (userId: string) =>
      fetchAPI(`/api/v1/rosters/?user_id=${userId}`),
    get: (rosterId: string) =>
      fetchAPI(`/api/v1/rosters/${rosterId}`),
    create: (data: {
      team_name: string;
      season?: string;
      jersey_color_primary?: string;
      jersey_color_secondary?: string;
      user_id: string;
      players: { name: string; jersey_number: number; height_inches?: number; position?: string }[];
    }) =>
      fetchAPI("/api/v1/rosters/", { method: "POST", body: JSON.stringify(data) }),
    uploadPlayerPhoto: async (playerId: string, photo: File) => {
      const formData = new FormData();
      formData.append("photo", photo);
      const res = await fetch(`${API_URL}/api/v1/rosters/players/${playerId}/photo`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json();
    },
    uploadTeamPhoto: async (rosterId: string, photo: File) => {
      const formData = new FormData();
      formData.append("photo", photo);
      const res = await fetch(`${API_URL}/api/v1/rosters/${rosterId}/team-photo`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json();
    },
  },
  stats: {
    getGameStats: (gameId: string) =>
      fetchAPI(`/api/v1/stats/game/${gameId}`),
    getGameSummary: (gameId: string) =>
      fetchAPI(`/api/v1/stats/game/${gameId}/summary`),
  },
  clips: {
    getGameClips: (gameId: string, eventType?: string) => {
      const params = eventType ? `?event_type=${eventType}` : "";
      return fetchAPI(`/api/v1/clips/game/${gameId}${params}`);
    },
  },
  files: {
    getUrl: (fileKey: string) => `${API_URL}/api/v1/files/${fileKey}`,
  },
};
