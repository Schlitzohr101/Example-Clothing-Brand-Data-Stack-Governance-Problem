# Memory Index

- [MinIO image: use community, not AIStor](arch_minio_community.md) — AIStor denies all S3 ops without a paid license; community minio/minio is the right choice
- [Nessie 0.107.x S3 credential config](arch_nessie_secret_urn.md) — inline access-key/secret-key rejected; must use urn:nessie-secret reference
- [ELT timestamp precision](arch_elt_timestamp_us.md) — Iceberg only supports microsecond timestamps; pandas ns must be downcast
