import type { Metadata } from "next";
import { BottomNav } from "@/components/layout/BottomNav";
import { TelegramInit } from "@/components/TelegramInit";
import { LanguageProvider } from "@/contexts/LanguageContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "NeuroSave",
  description: "Personal assistant mini app",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" className="h-full">
      <body className="min-h-full bg-tg-bg text-tg-text antialiased">
        <TelegramInit />
        <LanguageProvider>
          <main className="max-w-lg mx-auto px-4 pt-5 pb-24">{children}</main>
          <BottomNav />
        </LanguageProvider>
      </body>
    </html>
  );
}
