-- Migración inicial: crea los 4 schemas y todas las tablas + vistas.
-- Es la primera y única migración hasta hoy.
-- Para aplicar:   psql $DATABASE_URL -f db/migrations/0001_init.sql
-- Y después seed: psql $DATABASE_URL -f db/seed.sql

\i ../schema.sql
