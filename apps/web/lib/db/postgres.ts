import postgres from "postgres";

type SqlClient = ReturnType<typeof postgres>;

let client: SqlClient | undefined;
let clientUrl: string | undefined;

function isLocalDatabase(url: string): boolean {
  try {
    const hostname = new URL(url).hostname;
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
  } catch {
    return false;
  }
}

export function getDatabase(): SqlClient | null {
  const url = process.env.DATABASE_URL?.trim();

  if (!url) {
    return null;
  }

  if (!client || clientUrl !== url) {
    client = postgres(url, {
      connect_timeout: 10,
      idle_timeout: 20,
      max: 2,
      prepare: false,
      ssl: isLocalDatabase(url) ? false : "require",
    });
    clientUrl = url;
  }

  return client;
}
