# WriterLM — Frontend Studio

The frontend is a **React + Vite** web application organized as a **npm workspace monorepo**. It provides the WriterLM Studio UI — a developer-centric dashboard for creating, monitoring, and downloading AI-generated books.

---

## Monorepo Structure

```
web/frontend/
├── apps/
│   └── studio/             # The main Vite + React application
│       ├── src/
│       │   ├── App.tsx     # Root component, routing, auth guards
│       │   ├── api.ts      # Typed API client for all backend endpoints
│       │   ├── main.tsx    # App entrypoint, Clerk provider setup
│       │   ├── styles.css  # Global design tokens and base styles
│       │   ├── pages/      # Full-page route components
│       │   └── components/ # Shared UI components
│       ├── vite.config.ts
│       └── package.json
├── packages/
│   └── ui/                 # Shared, reusable component library
├── package.json            # Monorepo root (npm workspaces)
├── Dockerfile              # Production Docker image (nginx-served)
└── nginx.conf              # Nginx config for SPA routing
```

### Key Packages

| Package | Description |
|---|---|
| `apps/studio` | The main Studio application |
| `packages/ui` | Shared component library used by the studio |

---

## Pages & Navigation

| Route | Page | Description |
|---|---|---|
| `/` | Landing Page | Marketing/home page for unauthenticated users |
| `/create` | Create | Book request form — topic, audience, tone, PDF upload |
| `/jobs` | Jobs | Real-time job list with live status polling |
| `/books` | Library | Archive of all completed generated books |
| `/keys` | API Keys | Manage provider keys (Google, Groq, Tavily, Firecrawl) |
| `/settings` | Settings | Configure pipeline parameters (models, concurrency, LaTeX) |

---

## Authentication

Authentication is handled by **Clerk**. The `main.tsx` wraps the app in a `<ClerkProvider>` and the backend JWT is retrieved via Clerk's session token, passed as a `Bearer` token on every API request.

---

## Local Development Setup

### Prerequisites

- **Node.js 20+** and **npm 10+**

### 1. Install Dependencies

From the `web/frontend/` directory:

```bash
npm install
```

### 2. Environment Variables

Copy the example and fill in your Clerk keys:

```bash
cp .env.example .env
```

Required variables:

```bash
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_URL=http://localhost:8000  # Point to your running backend
```

### 3. Run the Dev Server

```bash
# From web/frontend/
npm run dev

# Or from the repo root:
# cd web/frontend && npm run dev
```

The Studio will be available at `http://localhost:5173`.

> The dev server uses **nodemon** to watch both `apps/studio` and `packages/ui` for changes and automatically restarts Vite.

### 4. Build for Production

```bash
npm run build
```

The compiled output lands in `apps/studio/dist/` and is served by nginx in the Docker image.

---

## Running with Docker

From the repo root:

```bash
docker-compose up --build frontend
```

The Studio will be served at `http://localhost:8080`.

---

## API Client (`api.ts`)

All communication with the backend is centralized in `apps/studio/src/api.ts`. It exports typed async functions for every backend endpoint (e.g., `createJob`, `listJobs`, `upsertApiKey`). When adding new backend endpoints, the corresponding typed function should be added here first before being consumed in components or pages.
