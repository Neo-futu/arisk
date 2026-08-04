# Contract Single Source of Truth

This project uses layered responsibilities with one API contract source for business domain models.

## Layer Responsibilities

- `frontend/`: page state, query orchestration, view mapping.
- `backend/`: authn/authz, aggregation/proxy, audit, policy checks.
- `2_processing/`: stable business calculations, data definitions, performance optimization.

## Contract Strategy

- Business contract source: `2_processing` OpenAPI.
- IAM/admin contract source: `backend` OpenAPI.
- Frontend generated clients/types consume contract snapshots from `frontend/openapi/`.

## Files

- Contract sync script: `scripts/sync_openapi_contracts.py`
- Backend generator config: `frontend/openapi-ts.config.ts`
- Processing generator config: `frontend/openapi-ts.processing.config.ts`
- Synced contract snapshots:
  - `frontend/openapi/backend.json`
  - `frontend/openapi/processing.json`

## Workflow

1. Start services:
   - backend: `http://localhost:8000`
   - processing: `http://localhost:8001`
2. Sync OpenAPI contracts:
   - `python scripts/sync_openapi_contracts.py`
3. Generate frontend clients/types:
   - `cd frontend`
   - `npm run generate-client`
   - `npm run generate-client:processing`

## Rules to Avoid Model Drift

- Do not hand-duplicate the same business DTO in three layers.
- Add/modify fields first in `2_processing` endpoint response models/contracts.
- Regenerate frontend processing types from `frontend/openapi/processing.json`.
- Backend proxy layer should only add minimal adaptation where required (auth, policy, error mapping).

## Endpoint Implementation Template

1. `2_processing/api/routers/*.py`: define endpoint and response contract.
2. `2_processing/tools/**/*.py`: implement calculation and DB queries.
3. `backend/app/api/routes/fsi/*.py`: proxy route with auth and policy.
4. `frontend/src/fsiClient.ts` or generated processing client: consume endpoint.
5. Frontend route page: query orchestration + UI mapping.

## Notes

- Keep contract snapshots versioned in Git for reviewability.
- For breaking changes, regenerate clients in the same PR and update affected pages together.
