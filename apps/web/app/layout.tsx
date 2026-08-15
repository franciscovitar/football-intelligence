import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { siteConfig } from "@/lib/site-config";

import "./globals.css";

export const metadata: Metadata = { title: { default: siteConfig.name, template: `%s · ${siteConfig.name}` }, description: siteConfig.description };
const PRIMARY = [["/", "Inicio"], ["/rankings", "Jugadores"], ["/team-rankings", "Equipos"], ["/compare", "Comparar"], ["/radar", "Radar"], ["/watchlist", "Watchlist"], ["/results-vs-performance", "Resultados vs rendimiento"], ["/sources", "Fuentes"]] as const;

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="es"><body><div className="app-frame"><header className="site-header"><Link className="brand" href="/"><span className="brand-mark" aria-hidden="true">FI</span><span><strong>Football Intelligence</strong><small>Evidence over noise</small></span></Link><nav className="site-nav" aria-label="Navegación principal">{PRIMARY.map(([href, label]) => <Link href={href} key={href}>{label}</Link>)}</nav></header>{children}<footer className="site-footer"><span>Football Intelligence · inteligencia V2 explicable</span><span><Link href="/lab">Lab técnico</Link> · los scores se leen con confianza y evidencia.</span></footer></div></body></html>;
}
