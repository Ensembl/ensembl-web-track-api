# Commands to give the read-only k8s user access to the tables created under the read/write user db schema.
# Run this after the database inititation and every time tables are altered (Django migration commands).
psql -h pgsql-hlvm-011.ebi.ac.uk -p 5432 -d <db_name> -U <ro_user> -W # Fill in the details
GRANT SELECT ON ALL TABLES IN SCHEMA <rw_user> TO <ro_user>; # Fill the gaps, run in the psql shell