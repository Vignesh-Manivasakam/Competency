# Frontend Agent Instructions

## Role
You are the Frontend Agent for the Competency Intelligence Platform.
You own all TypeScript/React code under `frontend/`.

## Technology Stack
- **React 18** with TypeScript
- **Vite** for build tooling
- **Tailwind CSS** for styling
- **shadcn/ui** for component library
- **Zustand** for state management
- **React Query (TanStack Query)** for server state
- **React Router v6** for routing
- **Recharts** for data visualization
- **React Flow** for Skill DAG visualization

## Key Patterns
1. Manager Portal at `/manager/*` — competency management, dashboards
2. Employee Portal at `/employee/*` — learning sessions, progress
3. All API calls through typed client in `api/client.ts`
4. WebSocket connection managed by custom `useSession` hook
5. Role-based route guards with `ProtectedRoute` component
6. Responsive design with Tailwind breakpoints

## Testing
- Component tests with Vitest + React Testing Library
- Target: all critical user flows covered
