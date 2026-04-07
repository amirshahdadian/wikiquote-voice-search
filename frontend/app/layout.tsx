import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Lora } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

const lora = Lora({
  subsets: ["latin"],
  variable: "--font-lora",
  display: "swap",
  style: ["normal", "italic"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "WikiQuote Voice Search",
  description:
    "Voice-first Wikiquote search with speaker recognition and personalized TTS. Find any quote, hands-free.",
};

export const viewport: Viewport = {
  themeColor: "#07080f",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geist.variable} ${geistMono.variable} ${lora.variable} dark`}
    >
      <body className="min-h-dvh h-dvh overflow-hidden bg-[#07080f] text-white antialiased">
        {children}
      </body>
    </html>
  );
}
