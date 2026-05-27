import type { Metadata } from "next";
import "./globals.css";
import "@/styles/fullcalendar.css";

export const metadata: Metadata = {
  title: "Time Tracker",
  description: "ActivityWatch week timeline and habits",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
