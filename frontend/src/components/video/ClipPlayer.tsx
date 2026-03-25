"use client";

import { useEffect, useRef } from "react";

interface ClipPlayerProps {
  src: string;
  startTime?: number;
  autoPlay?: boolean;
}

export default function ClipPlayer({
  src,
  startTime = 0,
  autoPlay = false,
}: ClipPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current && startTime > 0) {
      videoRef.current.currentTime = startTime;
    }
  }, [startTime]);

  return (
    <div className="relative rounded-lg overflow-hidden bg-black">
      <video
        ref={videoRef}
        src={src}
        controls
        autoPlay={autoPlay}
        className="w-full aspect-video"
      />
    </div>
  );
}
