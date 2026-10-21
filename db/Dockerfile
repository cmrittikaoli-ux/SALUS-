# PostgreSQL 16 + PostGIS + pg_cron
FROM postgis/postgis:16-3.4
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-cron \
 && rm -rf /var/lib/apt/lists/*
