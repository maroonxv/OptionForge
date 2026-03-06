# Postgres Init Scripts

Put optional bootstrap SQL or shell scripts in this directory.

- `*.sql`, `*.sql.gz`, `*.sh` files are executed only when the data directory is empty.
- Files in this directory are mounted read-only into `/docker-entrypoint-initdb.d`.
