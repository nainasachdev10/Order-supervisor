import "./globals.css";
import Link from "next/link";

export const metadata = {
  title: "Order Supervisor",
  description: "Long-running AI supervisor POC over Temporal",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="max-w-6xl mx-auto px-6 py-6">
          <header className="flex items-center justify-between mb-8">
            <Link href="/" className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-accent inline-block" />
              <span className="font-semibold tracking-tight">order-supervisor</span>
            </Link>
            <nav className="flex gap-4 text-sm text-gray-400">
              <Link href="/" className="hover:text-white">runs</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
