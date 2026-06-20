# Deploying VidStega to Fly.io

## Prerequisites

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Log in
fly auth login
```

## First-time setup

### 1. Create the web app

```bash
fly apps create vidstega
```

### 2. Set the secret key

```bash
fly secrets set SECRET_KEY=$(openssl rand -hex 32) --app vidstega
```

### 3. Provision Redis (Upstash)

```bash
fly ext upstash-redis create --app vidstega --name vidstega-redis
```

This automatically injects `REDIS_URL` into your app. Then tell the app to use it:

```bash
fly secrets set \
  CELERY_BROKER_URL="$REDIS_URL" \
  CELERY_RESULT_BACKEND="$REDIS_URL" \
  --app vidstega
```

> **Note:** After running `fly ext upstash-redis create`, copy the `REDIS_URL` value from the output and substitute it in the command above.

### 4. Create persistent volumes

```bash
fly volumes create vidstega_data    --size 10 --region sin --app vidstega
fly volumes create vidstega_outputs --size 10 --region sin --app vidstega
```

### 5. Deploy the web app

```bash
fly deploy --app vidstega
```

Your app will be live at `https://vidstega.fly.dev`.

---

## Celery worker (optional but recommended for async processing)

The web app falls back to synchronous processing if no worker is running, but for large videos you should run the worker.

### Create the worker app

```bash
fly apps create vidstega-worker

# Share the same secrets
fly secrets set \
  SECRET_KEY=<same-value-as-web> \
  CELERY_BROKER_URL=<redis-url> \
  CELERY_RESULT_BACKEND=<redis-url> \
  --app vidstega-worker
```

### Deploy the worker

```bash
fly deploy \
  --config fly-worker.toml \
  --app vidstega-worker \
  --override-cmd "celery -A celery_worker.celery_app worker --loglevel=info --concurrency=2"
```

---

## Subsequent deployments

```bash
fly deploy --app vidstega
```

## Useful commands

```bash
fly logs --app vidstega          # stream logs
fly ssh console --app vidstega   # shell into the running machine
fly status --app vidstega        # machine health
fly volumes list --app vidstega  # check volumes
```

## Region codes

Change `sin` (Singapore) in `fly.toml` and the volume create commands to the region nearest your users:

| Code | Region |
|------|--------|
| sin  | Singapore |
| nrt  | Tokyo |
| syd  | Sydney |
| lhr  | London |
| iad  | Washington DC |
| sjc  | San Jose |

Full list: `fly platform regions`
