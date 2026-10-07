-- Platform baseline.
--
-- Intentionally contains no product tables. Product tables, Row Level Security
-- policies, and storage buckets are added in later, separately reviewed
-- migrations.
create extension if not exists vector;
