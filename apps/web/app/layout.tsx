import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { siteConfig } from "@/lib/site-config";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: siteConfig.name,
    template: `%s · ${siteConfig.name}`,
  },
  description: siteConfig.description,
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <div className="app-frame">
          <header className="site-header">
            <Link className="brand" href="/">
              <span className="brand-mark" aria-hidden="true">
                FI
              </span>
              <span>
                <strong>Football Intelligence</strong>
                <small>Evidence over noise</small>
              </span>
            </Link>
            <nav className="site-nav" aria-label="Navegación principal">
              <Link href="/">Inicio</Link>
              <Link href="/rankings">Rankings</Link>
              <Link href="/teams">Equipos</Link>
              <Link href="/meta">Meta</Link>
              <Link href="/lab">Lab</Link>
            </nav>
          </header>
          {children}
          <footer className="site-footer">
            <span>Football Intelligence · modelo explicable y versionado</span>
            <span>Los scores se leen siempre junto con su confianza.</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
