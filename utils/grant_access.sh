# Commands to give the read-only k8s user access to the tables created under the read/write user db schema.
# Run this after the database inititation and every time tables are altered (Django migration commands).
psql -h <DB_HOST> -p 5432 -d <DB_NAME> -U <RW_USER> -W # Fill in the details
GRANT SELECT ON ALL TABLES IN SCHEMA <RW_USER> TO <RO_USER>; # Fill the gaps, run in the psql shell