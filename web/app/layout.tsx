import type { Metadata, Viewport } from "next";
import { BottomTabs, MobileDeskLinks } from "@/components/shell/bottom-tabs";
import { TopBar } from "@/components/shell/top-bar";
import { InstallBanner, InstallHelp } from "@/components/shell/install-banner";
import { SwRegister } from "@/components/shell/sw-register";
import { ToastProvider } from "@/components/ui/toast";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Cadence HR", template: "%s · Cadence HR" },
  description: "Internal HR operations desk: candidate records, CV search, hiring requests and reviews.",
  appleWebApp: { capable: true, title: "Cadence", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = { themeColor: "#0b3954" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-panel focus:px-3 focus:py-2 focus:text-ink"
        >
          Skip to main content
        </a>
        <ToastProvider>
          <TopBar />
          <main id="main" className="mx-auto max-w-[1200px] px-4 pb-24 pt-5 sm:px-6 md:pb-10">
            {children}
            <MobileDeskLinks />
          </main>
          <BottomTabs />
          <InstallBanner />
          <InstallHelp />
          <SwRegister />
        </ToastProvider>
      </body>
    </html>
  );
}
