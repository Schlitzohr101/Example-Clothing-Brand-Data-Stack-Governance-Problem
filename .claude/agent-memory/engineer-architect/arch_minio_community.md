---
name: arch_minio_community
description: MinIO must use the community minio/minio image, NOT the AIStor enterprise image, in the Meridian stack
metadata:
  type: project
---

The Meridian stack must use the community `minio/minio:latest` image for object storage, not the enterprise AIStor image (`quay.io/minio/aistor/minio:latest`).

**Why:** A prior attempt swapped in AIStor (commit "running into trouble with minIO and nessie not playing well together"). AIStor logs `No valid license found, running in offline mode. All S3 operations are denied.` and gates ALL S3 reads/writes behind a valid enterprise/SUBNET license. That breaks the entire lakehouse path (Nessie, Trino, ELT writes to the `lakehouse` bucket). The license token in `.env`/`minio.license.txt` was a personal FREE-plan trial tied to a personal gmail — inappropriate and non-functional for a shared open-source example project. Also, the community `minio/mc` client has no `mc admin license update` command, so the `minio-init` license step exited 1 and cascaded the whole `make elt` run.

**How to apply:** If anyone re-introduces the AIStor image or a `mc license update` step in `minio-init`, revert it. The `minio-init` job should only: set the `local` alias, `mc mb --ignore-existing local/lakehouse`, and `mc anonymous set none local/lakehouse`. `minio.license.txt` is gitignored and now unused; `MINIO_LICENSE_KEY` was removed from `.env.example`. See [[arch_nessie_secret_urn]].
