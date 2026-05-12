import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Crime Video Agent Studio",
  description: "Script review and full-stack AI video generation studio"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
