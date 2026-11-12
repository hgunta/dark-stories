import { defineConfig } from "@neon/config/v1";

// Target project: orange-surf-25188586; branch: production.
// Postgres is native to every Neon project. The existing FastAPI backend
// uses psycopg for database access. Do not put connection secrets here.
// AI Gateway is used by the optional Python moderator routing.
// Realtime is provisioned, but subscriptions require authenticated sealed
// queries; private chat transcripts must never be exposed to browsers.
export default defineConfig({
  aiGateway: true,
  preview: { realtime: true },
});
