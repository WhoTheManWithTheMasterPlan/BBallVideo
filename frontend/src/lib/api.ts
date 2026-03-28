const API_URL = "";

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
  profiles: {
    list: (userId: string) =>
      fetchAPI(`/api/v1/profiles/?user_id=${userId}`),
    get: (profileId: string) =>
      fetchAPI(`/api/v1/profiles/${profileId}`),
    create: (data: {
      name: string;
      user_id: string;
      jersey_number?: number;
      team_color_primary?: string;
      team_color_secondary?: string;
    }) =>
      fetchAPI("/api/v1/profiles/", { method: "POST", body: JSON.stringify(data) }),
    uploadPhoto: async (profileId: string, photo: File) => {
      const formData = new FormData();
      formData.append("photo", photo);
      const res = await fetch(`${API_URL}/api/v1/profiles/${profileId}/photos`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json();
    },
    deletePhoto: (profileId: string, photoId: string) =>
      fetchAPI(`/api/v1/profiles/${profileId}/photos/${photoId}`, { method: "DELETE" }),
  },
  videos: {
    list: (userId: string) =>
      fetchAPI(`/api/v1/videos/?user_id=${userId}`),
    get: (videoId: string) =>
      fetchAPI(`/api/v1/videos/${videoId}`),
    create: (data: { title: string; opponent?: string; game_date?: string; user_id: string }) =>
      fetchAPI("/api/v1/videos/", { method: "POST", body: JSON.stringify(data) }),
    uploadFile: async (
      videoId: string,
      file: File,
      onProgress?: (percent: number) => void,
    ): Promise<{ file_key: string; size_mb: number }> => {
      const CHUNK_SIZE = 50 * 1024 * 1024; // 50MB — safely under Cloudflare's 100MB limit

      // Small files: single upload (original path)
      if (file.size <= CHUNK_SIZE) {
        const formData = new FormData();
        formData.append("video", file);

        return new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open("POST", `${API_URL}/api/v1/videos/${videoId}/upload`);

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
      }

      // Large files: chunked upload
      const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

      // 1. Init upload session
      const initForm = new FormData();
      initForm.append("filename", file.name);
      initForm.append("total_chunks", totalChunks.toString());
      initForm.append("total_size", file.size.toString());

      const initRes = await fetch(
        `${API_URL}/api/v1/videos/${videoId}/upload/init`,
        { method: "POST", body: initForm },
      );
      if (!initRes.ok) {
        const err = await initRes.json().catch(() => ({}));
        throw new Error(err.detail || `Init failed: ${initRes.status}`);
      }
      const { upload_id } = await initRes.json();

      // 2. Upload chunks sequentially
      for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const blob = file.slice(start, end);

        const chunkForm = new FormData();
        chunkForm.append("upload_id", upload_id);
        chunkForm.append("chunk_index", i.toString());
        chunkForm.append("chunk", blob, `chunk_${i}`);

        const chunkRes = await fetch(
          `${API_URL}/api/v1/videos/${videoId}/upload/chunk`,
          { method: "POST", body: chunkForm },
        );
        if (!chunkRes.ok) {
          const err = await chunkRes.json().catch(() => ({}));
          throw new Error(err.detail || `Chunk ${i} failed: ${chunkRes.status}`);
        }

        if (onProgress) {
          onProgress(Math.round(((i + 1) / totalChunks) * 100));
        }
      }

      // 3. Complete — reassemble on server
      const completeForm = new FormData();
      completeForm.append("upload_id", upload_id);

      const completeRes = await fetch(
        `${API_URL}/api/v1/videos/${videoId}/upload/complete`,
        { method: "POST", body: completeForm },
      );
      if (!completeRes.ok) {
        const err = await completeRes.json().catch(() => ({}));
        throw new Error(err.detail || `Complete failed: ${completeRes.status}`);
      }

      return completeRes.json();
    },
    triggerProcessing: async (videoId: string, profileId: string) => {
      const formData = new FormData();
      formData.append("profile_id", profileId);
      const res = await fetch(`${API_URL}/api/v1/videos/${videoId}/process`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Process trigger failed: ${res.status}`);
      return res.json();
    },
  },
  jobs: {
    get: (jobId: string) =>
      fetchAPI(`/api/v1/jobs/${jobId}`),
    listByProfile: (profileId: string) =>
      fetchAPI(`/api/v1/jobs/profile/${profileId}`),
    listByVideo: (videoId: string) =>
      fetchAPI(`/api/v1/jobs/video/${videoId}`),
  },
  highlights: {
    listByJob: (jobId: string, eventType?: string) => {
      const params = eventType ? `?event_type=${eventType}` : "";
      return fetchAPI(`/api/v1/highlights/job/${jobId}${params}`);
    },
    listByProfile: (profileId: string, eventType?: string) => {
      const params = eventType ? `?event_type=${eventType}` : "";
      return fetchAPI(`/api/v1/highlights/profile/${profileId}${params}`);
    },
  },
  stats: {
    listByJob: (jobId: string) =>
      fetchAPI(`/api/v1/stats/job/${jobId}`),
    profileSummary: (profileId: string) =>
      fetchAPI(`/api/v1/stats/profile/${profileId}/summary`),
  },
  files: {
    getUrl: (fileKey: string) => `${API_URL}/api/v1/files/${fileKey}`,
  },
};
