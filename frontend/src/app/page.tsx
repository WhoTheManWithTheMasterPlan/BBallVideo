import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen p-8">
      <h1 className="text-5xl font-bold mb-4">BBallVideo</h1>
      <p className="text-xl text-gray-400 mb-8 text-center max-w-lg">
        AI-powered basketball game film analysis. Upload your sideline footage
        and get instant stats, clips, and court visualizations.
      </p>
      <div className="flex gap-4">
        <Link
          href="/dashboard"
          className="px-6 py-3 bg-orange-600 hover:bg-orange-700 rounded-lg font-medium transition-colors"
        >
          Go to Dashboard
        </Link>
        <Link
          href="/upload"
          className="px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg font-medium transition-colors"
        >
          Upload Game
        </Link>
      </div>
    </main>
  );
}
