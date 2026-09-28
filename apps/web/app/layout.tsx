import type { Metadata } from "next";
import "./styles.css";
import { Navbar } from "./components/Navbar";

export const metadata: Metadata = { title: "ProcureFind", description: "Permission-first supplier offer search" };

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        {children}
      </body>
    </html>
  );
}
