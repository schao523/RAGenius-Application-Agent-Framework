SELECT 'CREATE DATABASE ragenius_execution OWNER ragenius'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'ragenius_execution'
)\gexec
