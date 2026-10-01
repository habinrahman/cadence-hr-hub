import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { BottomTabs } from "@/components/shell/bottom-tabs";
import { Header } from "@/components/shell/header";
import { InstallBanner, InstallHelp } from "@/components/shell/install-banner";
import { Sidebar } from "@/components/shell/sidebar";
import { SwRegister } from "@/components/shell/sw-register";
import { ToastProvider } from "@/components/ui/toast";
import "./globals.css";

const sans = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Cadence HR", template: "%s · Cadence HR" },
  description: "Internal HR operations desk: candidate records, CV search, hiring requests and reviews.",
  appleWebApp: { capable: true, title: "Cadence", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = { themeColor: "#111c32" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-panel focus:px-3 focus:py-2 focus:text-ink"
        >
          Skip to main content
        </a>
        <ToastProvider>
          <div className="flex min-h-dvh">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Header />
              <main id="main" className="w-full max-w-[1320px] px-4 pb-24 pt-7 sm:px-8 md:pb-12 lg:px-11 lg:pt-10">
                {children}
              </main>
            </div>
          </div>
          <BottomTabs />
          <InstallBanner />
          <InstallHelp />
          <SwRegister />
        </ToastProvider>
      </body>
    </html>
  );
}
