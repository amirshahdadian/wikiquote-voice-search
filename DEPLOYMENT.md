# Deployment

This app is now containerized as two deployable services:

- `backend/Dockerfile`: FastAPI, Neo4j Aura, and Linux ASR with `ASR_BACKEND=faster`.
- `frontend/Dockerfile`: Next.js standalone production server.

## Local Docker

Copy `.env.example` to `.env`, fill in the Neo4j Aura credentials, then run:

```bash
docker compose build
docker compose up
```

Open `http://localhost:3000`. The backend health endpoint is `http://localhost:8000/api/health`.

## ASR Backends

Use environment variables to select the speech-recognition provider:

```bash
# Apple Silicon local development
ASR_BACKEND=mlx
ASR_MODEL_NAME=mlx-community/whisper-large-v3-turbo

# Linux/Azure containers
ASR_BACKEND=faster
ASR_MODEL_NAME=Systran/faster-whisper-small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
ASR_BEAM_SIZE=5
```

`mlx-whisper` is intentionally optional because it is Apple Silicon-specific. For local MLX development, install:

```bash
python -m pip install ".[mlx]"
```

## Azure Container Apps

Recommended shape:

- Deploy backend and frontend as separate Azure Container Apps.
- Expose frontend with external ingress on port `3000`.
- Expose backend with external ingress on port `8000`, or internal ingress if you add an API gateway/reverse proxy later.
- Store `NEO4J_PASSWORD` as an Azure secret, not an image variable.
- Set backend `FRONTEND_ORIGINS` to the deployed frontend URL.
- Build the frontend image with `NEXT_PUBLIC_API_BASE_URL` set to the deployed backend URL.

Example build and push:

```bash
ACR_NAME=<your-acr-name>
BACKEND_IMAGE=$ACR_NAME.azurecr.io/wikiquote-backend:latest
FRONTEND_IMAGE=$ACR_NAME.azurecr.io/wikiquote-frontend:latest
BACKEND_URL=https://<backend-container-app-fqdn>

az acr login --name "$ACR_NAME"

docker build -f backend/Dockerfile -t "$BACKEND_IMAGE" .
docker push "$BACKEND_IMAGE"

docker build \
  --build-arg NEXT_PUBLIC_API_BASE_URL="$BACKEND_URL" \
  -f frontend/Dockerfile \
  -t "$FRONTEND_IMAGE" \
  frontend
docker push "$FRONTEND_IMAGE"
```

Backend runtime settings for Azure:

```bash
ASR_BACKEND=faster
ASR_MODEL_NAME=Systran/faster-whisper-small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
NEO4J_URI=neo4j+s://<your-aura-host>.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<secret>
NEO4J_DATABASE=<optional-aura-database-name>
FRONTEND_ORIGINS=https://<frontend-container-app-fqdn>
DATA_DIR=/app/data
```

## Neo4j Aura

Use the Aura connection URI from the Aura console. For AuraDB, prefer `neo4j+s://...` because it uses encrypted Bolt with certificate validation. Keep the username and password in Azure secrets. If an enterprise network blocks Bolt, Aura also documents HTTPS Query API fallback paths, but this app currently uses the official Neo4j Python driver over Bolt.

## References Used

- Azure Container Apps ingress and target ports: https://learn.microsoft.com/azure/container-apps/ingress-overview
- Azure Container Apps health probes: https://learn.microsoft.com/azure/container-apps/health-probes
- Azure FastAPI container deployment path: https://learn.microsoft.com/azure/developer/python/tutorial-containerize-simple-web-app-for-app-service
- Neo4j Aura application connections: https://neo4j.com/docs/aura/connecting-applications/overview/
- Neo4j Aura connection schemes: https://www.neo4j.com/docs/aura/getting-started/connect-instance/
- Docker/Next.js standalone guidance: https://docs.docker.com/guides/nextjs/containerize/
- Next.js standalone output docs: https://github.com/vercel/next.js/blob/v16.1.6/docs/01-app/03-api-reference/05-config/01-next-config-js/output.mdx
- Faster Whisper provider API: https://github.com/SYSTRAN/faster-whisper
