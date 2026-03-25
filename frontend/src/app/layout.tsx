import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BBallVideo - AI Basketball Analysis",
  description: "AI-powered game film breakdown for coaches",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-white min-h-screen">{children}</body>
    </html>
  );
}
