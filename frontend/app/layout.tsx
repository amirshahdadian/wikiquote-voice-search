import type { Metadata } from "next";
import { Manrope, Work_Sans } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-headline",
});

const workSans = Work_Sans({
  subsets: ["latin"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "Which Quote",
  description: "Voice-first Wikiquote search with speaker recognition and personalized TTS.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${manrope.variable} ${workSans.variable} min-h-screen bg-scholarly-background text-ink antialiased`}>
        <div className="relative isolate overflow-x-hidden">
          {children}
        </div>
      </body>
    </html>
  );
}
