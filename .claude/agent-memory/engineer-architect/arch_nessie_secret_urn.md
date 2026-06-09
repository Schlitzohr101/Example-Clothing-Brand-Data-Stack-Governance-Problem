---
name: arch_nessie_secret_urn
description: Nessie 0.107.x requires S3 credentials via urn:nessie-secret reference, not inline access-key/secret-key
metadata:
  type: project
---

In Nessie 0.107.x (pinned here: `ghcr.io/projectnessie/nessie:0.107.9`), the S3 catalog credentials under `nessie.catalog.service.s3.default-options` can no longer be supplied inline. Inline `access-key`/`secret-key` cause this runtime error on table create: `Invalid secret URI, must be in the form 'urn:nessie-secret:<provider>:<secret-name>'`.

**Why:** The S3 credential config schema changed between 0.92.x (original pin) and 0.107.x. Secrets must now be referenced via a secret URN, with actual values defined as a name/secret pair.

**How to apply:** Use this form in the nessie service env (provider is `quarkus`):
```
nessie.catalog.service.s3.default-options.access-key=urn:nessie-secret:quarkus:nessie.catalog.secrets.s3-default
nessie.catalog.secrets.s3-default.name=<access-key-id>
nessie.catalog.secrets.s3-default.secret=<secret-key>
```
`.name` = access key id, `.secret` = secret key. Keep `auth-type=STATIC`, `endpoint`, `region`, `path-style-access` as-is. Nessie's warehouse is referenced by name `warehouse` in compose, but pyiceberg/Trino pass `s3://lakehouse/`. See [[arch_minio_community]].
