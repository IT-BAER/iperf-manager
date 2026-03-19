# iperf-manager Frontend

This directory contains the React 19 + TypeScript + Vite frontend for the iperf-manager web dashboard.

## Stack

- React 19
- TypeScript 5
- Vite 8
- Tailwind CSS 3
- Chart.js + react-chartjs-2
- Socket.IO client
- Font Awesome 7

## Commands

Install dependencies:

```bash
npm install
```

Start the Vite development server:

```bash
npm run dev
```

Build the production bundle:

```bash
npm run build
```

Run ESLint:

```bash
npm run lint
```

Preview the built bundle:

```bash
npm run preview
```

## Runtime Notes

- The built output goes to `web/frontend/dist/`.
- Flask serves that `dist/` bundle when it exists.
- If `dist/` is missing, the backend falls back to the legacy `templates/dashboard.html` implementation.
- On a fresh page load, the sidebar performs one silent auto-discovery pass before the manual Discover button becomes idle again.

## Key Files

| Path | Purpose |
|------|---------|
| `src/App.tsx` | App shell, reports list, agent discovery and refresh wiring |
| `src/components/TestConfig.tsx` | Test configuration panel and topology integration |
| `src/components/TopologyDiagram.tsx` | Server/client topology and live connection visuals |
| `src/components/LiveResults.tsx` | Live KPI cards and charts |
| `src/components/ReportViewer.tsx` | Inline CSV report viewer |
| `src/components/Sidebar.tsx` | Agent list, discovery, refresh, manual add |
| `src/index.css` | Shared component classes and dashboard styling |
| `tailwind.config.js` | Theme tokens used throughout the UI |

## Integration Points

- REST API calls go through `src/api.ts`.
- Live updates come from `src/hooks/useSocket.ts`.
- The frontend talks to Flask routes under `/api/*` and receives Socket.IO events such as `status`, `metrics`, `test_started`, `test_completed`, and `agents_update`.
