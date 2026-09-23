import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = { title: "ProcureFind", description: "Permission-first supplier offer search" };

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="brand-lockup">
          <span>AI Procurement Agent</span>
          <img src="/mccia-logo-cropped.png" alt="MCCIA" className="mccia-logo" />
        </div>
        {children}
      </body>
    </html>
  );
}
