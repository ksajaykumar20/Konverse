import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Konverse · Tenant dashboard",
  description: "Manage documents, chat, and sessions for a Konverse tenant.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}