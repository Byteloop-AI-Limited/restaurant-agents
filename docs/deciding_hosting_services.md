# Hosting Decision Questionnaire — FastAPI service

**Purpose:** determine the best always-on container host (Fly.io / Render / Google Cloud Run / AWS ECS Express Mode / Cloudflare Containers / Cloudflare Workers) for this service.

**Context for the agent:** this is a FastAPI app (Docker-based) that registers webhook handlers for WhatsApp, Stripe, and Ordelo, with an AI agent running behind the endpoints. It currently runs on AWS Lambda and is being migrated. It is intended to be stateless / ephemeral. The single hard requirement is **no double execution** of the agent loop.

**How to answer:** read the code and answer each question factually. Do **not** guess — if something isn't in the codebase, answer `NOT FOUND IN CODE`. Quote file paths / function names where relevant. The decision key at the end maps your answers to a recommendation.

---

## Section A — Workload shape (these are the decisive questions)

1. Do any webhook or endpoint handlers kick off work that runs longer than ~30 seconds (up to minutes)? List each, with the file/function and how the work is spawned (FastAPI `BackgroundTasks`, `asyncio.create_task`, a thread, Celery/RQ, a subprocess, etc.).
2. What is the longest a single background/agent task can run — typical and worst case?
3. Is there a scheduled or polling job (e.g. runs every ~10 minutes)? Is it defined **in-process** (APScheduler, an `asyncio` loop, a `while True` + sleep) or does it rely on an **external** trigger (cron, Cloud Scheduler, EventBridge)? Give the file/function.
4. After the HTTP response is returned, does the process still need to keep doing work (fire-and-forget after ack)? Or does every handler finish all its work before responding?

> Why these decide it: real minutes-long work after the response ⇒ you need an always-on container, which rules out plain Workers/Lambda and makes Cloudflare Containers' scale-to-sleep model costly. If every handler is quick, Cloudflare Workers become viable and likely cheapest.

---

## Section B — Idempotency & double execution (the one requirement)

5. For each webhook source (Stripe, WhatsApp, Ordelo): does the handler return a 2xx **before** doing heavy work, or does it process inline and then respond? Give the file/function for each.
6. Is there any deduplication / idempotency keyed on the provider's event ID (Stripe `event.id`, WhatsApp message id, Ordelo equivalent)? Where is the dedup record stored — in-memory `set`/`dict`, Redis, a DB unique constraint, nowhere?
7. Does the code rely on **in-memory** state (a `set`, `dict`, `asyncio.Lock`, etc.) to prevent duplicate processing? If so, name it and the file.
8. Is webhook **signature verification** implemented for each provider?
9. If the exact same event is delivered twice (providers retry), are the handler's side effects idempotent (safe to run twice)? Or would a duplicate cause a duplicate order / payment / message?

> Why: "no double execution" is mostly an application-layer concern — providers retry if you ack slowly. Fast 2xx + dedup on event ID solves it on any host. But **in-memory dedup only works if you run exactly one instance** (see B7 → E), so this determines whether you can autoscale.

---

## Section C — State & concurrency

10. Does the app write to local disk or depend on the local filesystem beyond throwaway scratch? Any SQLite files, local caches, or uploaded-file storage?
11. Does it hold in-memory state that must survive across requests — agent/conversation memory, session context, per-user caches?
12. Any long-lived connections — WebSocket, SSE, streaming responses?
13. How many web server workers does it start (Uvicorn/Gunicorn `--workers`, Uvicorn processes)? More than one worker means more than one process, which already breaks in-memory dedup.
14. Does anything in the code assume horizontal scale (multiple replicas), or is it written as a single-process app?

---

## Section D — Resource footprint & cost drivers

15. Peak memory usage — including anything the agent loads in-process (models, embeddings, large libraries)? Baseline idle memory?
16. Is the agent CPU-bound locally, or mostly **waiting on external LLM/API calls** (I/O-bound)?
17. Boot / cold-start time: how long from container start to serving the first request (imports, model loads, warm-up)?
18. Rough outbound egress per month (LLM API payloads, WhatsApp media, etc.)?
19. Expected request pattern: steady low trickle, or spiky (e.g. order-time bursts)? Roughly how many webhook events/day?

> Why: high in-process memory makes Cloudflare Containers expensive (memory is billed on provisioned size while the container is awake). Long boot times make scale-to-zero painful. Burstiness is the only thing that would favour a scale-to-zero model.

---

## Section E — Ops, deploy & compliance

20. Is there a `Dockerfile`? Note the base image, approximate image size, and any native/system dependencies.
21. Is `SIGTERM` / graceful shutdown handled so an in-flight multi-minute task can drain before the process exits?
22. Are there any data-residency constraints on payment or customer data (UK/EU-only processing)?
23. What external services are already in the stack (Redis, Postgres, a message queue, object storage)? Name them and how they're used.
24. How are secrets/env vars injected and expected to be provided at runtime?
25. Is there a health-check endpoint suitable for a load balancer / platform probe? (Confirm the path.)

> Why: **if Redis or a DB unique constraint is available (Q23), you get a distributed lock** and can safely run more than one instance — which unlocks Cloud Run / ECS Express and removes the single-instance pin. Data residency (Q22) matters because Cloudflare defaults to "Region: Earth."

---

## Decision key (map the answers to a recommendation)

- **A1/A4 = yes (real minutes-long background work) AND B6/B7 rely on in-memory dedup with no external lock (E23 has no Redis/DB lock):**
  → **Single always-on container, pinned to exactly 1 instance.** Best options: **Fly.io** (cheapest, ~$6–12/mo) or **Render** (most predictable, ~$7/mo). Run the poll in-process (A3). Avoid Cloudflare Containers (sleep model + provisioned-memory cost) and plain Workers/Lambda.

- **A1 = no (all handlers finish in sub-second/seconds) AND C10/C11 confirm ephemeral:**
  → **Cloudflare Workers** likely wins — Cron Triggers cover the poll, Durable Objects give exactly-one processing per key. Use Cloudflare **Containers** only if you need a full Python runtime a Worker can't provide.

- **E23 shows Redis or a DB unique constraint available:**
  → Dedup no longer needs single-instance pinning. **Google Cloud Run** (`--min-instances=1 --no-cpu-throttling` for instance-based billing so background work runs) or **ECS Express** become viable and can autoscale safely.

- **D15 peak memory is multi-GB:**
  → Cloudflare Containers cost balloons (provisioned memory billed while awake). Favour **Fly.io / Render / Cloud Run**.

- **Already committed to AWS, or running several services:**
  → **ECS Express Mode** (up to 25 services share one ALB). For a single small service its ~$17/mo ALB floor makes it the priciest option here.

- **The 10-minute poll (A3):**
  → An in-process scheduler works on any always-on container. Only if you go scale-to-zero do you need a platform cron (Cloudflare Cron Triggers / Cloud Scheduler / EventBridge).

- **Data residency (Q22) = UK/EU required:**
  → Pin region explicitly. Straightforward on Fly/Render/Cloud Run; extra config on Cloudflare (Region: Earth by default).

---

## One-line summary to report back

After answering, state: **(a)** is there real minutes-long background work (yes/no), **(b)** is dedup in-memory or external, **(c)** is Redis/DB available, **(d)** peak memory. Those four answers alone decide it.
