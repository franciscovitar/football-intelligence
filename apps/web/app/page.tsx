import { siteConfig } from "@/lib/site-config";

export default function Home() {
  return (
    <main className="shell">
      <p className="eyebrow">FOUNDATION · BLOCK 1</p>
      <h1>{siteConfig.name}</h1>
      <p className="lede">
        La base técnica está lista. Los datos reales y el motor analítico llegan en los próximos bloques.
      </p>
    </main>
  );
}
