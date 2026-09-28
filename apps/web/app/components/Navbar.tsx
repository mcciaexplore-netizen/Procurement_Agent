"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type NavLink = { href: string; label: string };

const NAV_LINKS: NavLink[] = [
  { href: "/", label: "Search" },
  { href: "/admin", label: "Admin" },
];

function useScrollThreshold(threshold: number) {
  const [past, setPast] = useState(false);
  useEffect(() => {
    const onScroll = () => setPast(window.scrollY > threshold);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);
  return past;
}

export function Navbar() {
  const scrolled = useScrollThreshold(20);
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className={`site-navbar${scrolled ? " site-navbar--scrolled" : ""}`} aria-label="Main Navigation">
      <div className="site-navbar__row">
        <div className="site-navbar__brand">
          <img src="/mccia-logo.png" alt="MCCIA" className="site-navbar__logo" />
          <span className="site-navbar__divider" aria-hidden="true" />
          <div className="site-navbar__stack">
            <span className="site-navbar__title">
              <span className="site-navbar__title-full">AI Procurement Agent</span>
              <span className="site-navbar__title-short">AI Procurement</span>
            </span>
            <span className="site-navbar__tagline">MCCIA Enterprise Sourcing Hub</span>
          </div>
        </div>

        <nav className="site-navbar__links" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="site-navbar__link">
              {link.label}
            </Link>
          ))}
        </nav>

        <button
          type="button"
          className="site-navbar__menu-button"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span />
          <span />
          <span />
        </button>
      </div>

      {menuOpen && (
        <nav className="site-navbar__mobile-menu" aria-label="Mobile">
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="site-navbar__mobile-link" onClick={() => setMenuOpen(false)}>
              {link.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
