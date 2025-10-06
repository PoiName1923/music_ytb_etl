#!/bin/bash
set -e
# Bước 1: Tạo user và database.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Tạo người dùng thứ hai
    CREATE USER ${POSTGRES_USER_ETL} WITH PASSWORD '${POSTGRES_PASSWORD_ETL}';

    -- Tạo database thứ hai
    CREATE DATABASE ${POSTGRES_DB_ETL};

    -- Cấp tất cả các quyền trên database thứ hai cho người dùng thứ hai
    GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB_ETL} TO ${POSTGRES_USER_ETL};
EOSQL
echo "Second user and database created."

# Bước 2: Chạy script khởi tạo schema/table cho database của ứng dụng
echo "Initializing schema and tables for database '${POSTGRES_DB_ETL}'..."
psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER_ETL" \
    --dbname "$POSTGRES_DB_ETL" \
    -v app_user="${POSTGRES_USER_ETL}" \
    -v app_schema="${POSTGRES_SCHEMA_ETL}" \
    -f /docker-entrypoint-initdb.d/scripts/init-schema.sql
echo "Schema and tables initialized successfully."