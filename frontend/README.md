# Experience Budget — Frontend

React 19 + Vite dashboard for home-network experience comparison, live client
telemetry, and QoE-aware model intelligence.

The UI runs in **self-contained demo mode by default**: a clock-driven telemetry
generator supplies every API response, so all three pages stay populated and
update every second without a backend.

## Pages

| Route                 | Page                                     |
| --------------------- | ---------------------------------------- |
| `/compare`            | Baseline vs. optimized comparison        |
| `/model-intelligence` | Live model, pipeline, and inference data |
| `/live-control`       | Per-client live telemetry and QoE        |

`/` redirects to `/compare`. The app uses `BrowserRouter`, so hosting must
rewrite unknown paths to `index.html` (already configured for Vercel).

## Local development

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
```

Other scripts:

```bash
npm run lint       # ESLint
npm run build      # production build to dist/
npm run preview    # serve the production build locally
```

## Configuration

| Variable         | Default                 | Purpose                                             |
| ---------------- | ----------------------- | --------------------------------------------------- |
| `VITE_DEMO_MODE` | `true`                  | Serve live simulated telemetry; no backend needed.  |
| `VITE_API_BASE`  | `http://127.0.0.1:8000` | Real API origin; only used when demo mode is false. |

Demo mode is enabled unless `VITE_DEMO_MODE=false`. Deployment builds also set
`VITE_DEMO_MODE=true` in `.env.production`, so a hosted copy works with no
backend and no environment variables.

If you disable demo mode on Vercel, `VITE_API_BASE` must point to a publicly
reachable **HTTPS** backend; a localhost URL will not work from the browser.

## Deploy to Vercel

The repository includes deployment config for both common setups:

### Option A — import the repository root (recommended)

1. Push the repository to GitHub.
2. In Vercel, **Add New → Project** and import the repository.
3. Leave **Root Directory** empty (repository root) and click **Deploy**.

No other settings are required. The root [`vercel.json`](../vercel.json)
installs and builds the frontend, publishes `frontend/dist`, and rewrites all
routes to `index.html`.

### Option B — set Root Directory to `frontend`

1. Import the repository in Vercel.
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Vite**; build `npm run build`; output `dist`.
4. Click **Deploy**.

These values are already declared in [`vercel.json`](./vercel.json), so the
dashboard only needs the root directory change.

### Deploying from the CLI

```bash
npm i -g vercel
vercel           # preview deployment
vercel --prod    # production deployment
```

Run the CLI from the repository root for Option A, or from `frontend/` for
Option B.

## Post-deploy smoke test

1. Open the deployment URL — it should redirect to `/compare`.
2. Confirm values change every second and the sidebar shows Backend/Gateway
   badges as connected.
3. Visit `/model-intelligence` and `/live-control` directly (not only through
   in-app navigation) to confirm the SPA rewrite works.
4. Start and stop a scenario from the Compare page.
5. Open the browser console and confirm there are no errors.

## Demo-mode note

The dashboard is a simulated lab. Values are generated for demonstration and
should be described as "demo telemetry", not as live control of a real
household network.
