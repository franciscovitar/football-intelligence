import Link from "next/link";
import { connection } from "next/server";

import { DiagnosticFindingCard } from "@/features/diagnostics/finding-card";
import { DataNotice } from "@/features/players/data-notice";
import { PlayerRankingCard } from "@/features/players/player-ranking-card";
import { formatDateTime, formatScore, ROLE_LABELS_SINGULAR } from "@/lib/player-display";
import { getHomeDashboard } from "@/lib/queries/player-analytics";
import { getTopPlayerDiagnosticsByCode, type DiagnosticFinding } from "@/lib/queries/diagnostics";

function entityName(finding: DiagnosticFinding): string {
  const value = finding.supportingMetrics.player_name;
  return typeof value === "string" ? value : `Jugador #${finding.entityId}`;
}

export default async function HomePage() {
  await connection();
  const [result, breakoutResult, underratedResult, overratedResult] = await Promise.all([
    getHomeDashboard(),
    getTopPlayerDiagnosticsByCode("breakout_signal", 6),
    getTopPlayerDiagnosticsByCode("underrated", 6),
    getTopPlayerDiagnosticsByCode("overrated", 6),
  ]);

  return (
    <main className="page-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">FOOTBALL INTELLIGENCE · PLAYER V1</p>
          <h1>Qué está pasando de verdad.</h1>
          <p className="hero-copy">
            Rankings por rol, Forma reciente, Performance estabilizada y evidencia visible detrás
            de cada score. Sin depender de highlights ni de opiniones sueltas.
          </p>
          <div className="hero-actions">
            <Link className="button button-primary" href="/rankings">
              Explorar rankings
            </Link>
            <a className="button button-secondary" href="#method">
              Cómo leer los scores
            </a>
          </div>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          <span className="orbit-score">92</span>
          <span className="orbit-label">Performance</span>
          <span className="orbit-line" />
          <span className="orbit-note">stats → contexto → interpretación</span>
        </div>
      </section>

      {result.status !== "ready" ? (
        <DataNotice
          title={result.status === "unconfigured" ? "Base de datos pendiente" : "Datos no disponibles"}
          message={result.message}
        />
      ) : result.data.context === null ? (
        <DataNotice
          title="Todavía no hay snapshots"
          message="El read model está conectado, pero Player Analytics todavía no persistió rankings para este entorno."
        />
      ) : (
        <>
          <section className="context-strip" aria-label="Contexto del modelo">
            <div>
              <span>Scope</span>
              <strong>{result.data.context.scopeKey}</strong>
            </div>
            <div>
              <span>Modelo</span>
              <strong>{result.data.context.modelVersion}</strong>
            </div>
            <div>
              <span>Calculado</span>
              <strong>{formatDateTime(result.data.context.calculatedAt)}</strong>
            </div>
          </section>

          <section className="dashboard-grid">
            <div className="panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">PERFORMANCE</p>
                  <h2>Mejores del período</h2>
                </div>
                <Link href="/rankings?window=season">Ver todos</Link>
              </div>
              <div className="ranking-list">
                {result.data.performanceLeaders.map((player, index) => (
                  <PlayerRankingCard key={player.playerId} player={player} rank={index + 1} />
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">FORMA · LAST 5</p>
                  <h2>Los que llegan encendidos</h2>
                </div>
                <Link href="/rankings?window=last_5">Ver Forma</Link>
              </div>
              <div className="ranking-list">
                {result.data.formLeaders.map((player, index) => (
                  <PlayerRankingCard key={player.playerId} player={player} rank={index + 1} />
                ))}
              </div>
            </div>
          </section>

          <section className="panel trend-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">TREND</p>
                <h2>Quién está subiendo</h2>
              </div>
              <p>Forma últimos 5 vs Performance de temporada.</p>
            </div>
            <div className="trend-grid">
              {result.data.risingPlayers.map((player) => (
                <Link className="trend-card" href={`/player/${player.playerId}`} key={player.playerId}>
                  <div>
                    <span>{ROLE_LABELS_SINGULAR[player.role]}</span>
                    <h3>{player.playerName}</h3>
                  </div>
                  <div className="trend-score">
                    <strong className={player.delta >= 0 ? "positive" : "negative"}>
                      {player.delta >= 0 ? "+" : ""}
                      {formatScore(player.delta)}
                    </strong>
                    <span>
                      {formatScore(player.seasonScore)} → {formatScore(player.formScore)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </section>

          {breakoutResult.status === "ready" ? (
            <section className="panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">DIAGNOSTIC RULES</p>
                  <h2>Sorpresas</h2>
                </div>
                <p>Señal de breakout: nivel estable en subida frente a la expectativa histórica.</p>
              </div>
              {breakoutResult.data.length === 0 ? (
                <p className="ranking-summary">Sin señales de breakout en este cálculo.</p>
              ) : (
                <div className="ranking-list">
                  {breakoutResult.data.map((finding) => (
                    <DiagnosticFindingCard
                      entityHref={`/player/${finding.entityId}`}
                      entityName={entityName(finding)}
                      finding={finding}
                      key={`${finding.diagnosticCode}-${finding.entityId}`}
                    />
                  ))}
                </div>
              )}
            </section>
          ) : null}

          <section className="dashboard-grid">
            {underratedResult.status === "ready" ? (
              <div className="panel">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">DIAGNOSTIC RULES</p>
                    <h2>Infravalorados</h2>
                  </div>
                  <p>Rendimiento por encima de la percepción externa. No es valor de mercado.</p>
                </div>
                {underratedResult.data.length === 0 ? (
                  <p className="ranking-summary">Sin hallazgos de infravaloración en este cálculo.</p>
                ) : (
                  <div className="ranking-list">
                    {underratedResult.data.map((finding) => (
                      <DiagnosticFindingCard
                        entityHref={`/player/${finding.entityId}`}
                        entityName={entityName(finding)}
                        finding={finding}
                        key={`${finding.diagnosticCode}-${finding.entityId}`}
                      />
                    ))}
                  </div>
                )}
              </div>
            ) : null}

            {overratedResult.status === "ready" ? (
              <div className="panel">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">DIAGNOSTIC RULES</p>
                    <h2>Sobrevalorados</h2>
                  </div>
                  <p>Percepción externa por encima del rendimiento. No es valor de mercado.</p>
                </div>
                {overratedResult.data.length === 0 ? (
                  <p className="ranking-summary">Sin hallazgos de sobrevaloración en este cálculo.</p>
                ) : (
                  <div className="ranking-list">
                    {overratedResult.data.map((finding) => (
                      <DiagnosticFindingCard
                        entityHref={`/player/${finding.entityId}`}
                        entityName={entityName(finding)}
                        finding={finding}
                        key={`${finding.diagnosticCode}-${finding.entityId}`}
                      />
                    ))}
                  </div>
                )}
              </div>
            ) : null}
          </section>
        </>
      )}

      <section className="method-grid" id="method">
        <article>
          <span>01</span>
          <h2>Performance</h2>
          <p>
            Resume el nivel del jugador en la muestra de temporada disponible, comparándolo contra
            futbolistas de su mismo rol.
          </p>
        </article>
        <article>
          <span>02</span>
          <h2>Forma</h2>
          <p>
            Usa los últimos cinco partidos con mayor peso para lo más reciente. Sirve para detectar
            cambios rápidos sin confundir una racha corta con nivel estable.
          </p>
        </article>
        <article>
          <span>03</span>
          <h2>Confianza</h2>
          <p>
            Minutos, estabilidad de rol, tamaño de la muestra y cobertura de métricas. Un 90 con
            baja confianza no significa lo mismo que un 90 consolidado.
          </p>
        </article>
      </section>
    </main>
  );
}
