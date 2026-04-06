# GitHub Tech Doc Generator Vue Frontend Design

## Overview

This document defines the approved frontend design for the next phase of the GitHub Tech Doc Generator project.

The backend MVP already exists and provides:

- Task creation via `POST /api/v1/analyze`
- Task status via `GET /api/v1/tasks/{task_id}`
- Task result via `GET /api/v1/tasks/{task_id}/result`
- SSE progress via `GET /api/v1/tasks/{task_id}/stream`

This phase adds a Vue-based frontend that turns those APIs into a usable operator-facing workflow.

## Scope

This frontend phase includes:

- A Vue 3 application under `web/`
- Vite for local development and bundling
- Vue Router for a two-page flow
- A submission page for GitHub repository analysis
- A task detail page with status, progress timeline, and result display
- SSE progress consumption with polling fallback
- Responsive layouts for desktop and mobile

This frontend phase does not include:

- Authentication
- Task history across sessions
- Rich Markdown rendering
- Export to PDF or HTML
- Nuxt or SSR
- Pinia or global state management

## Recommended Approach

Three approaches were considered:

### 1. Lightweight page-level implementation

Build a minimal Vue app with page-local state and direct API calls in page components.

Trade-off:

- Fastest to start
- Easy to become tangled once status polling, SSE, and result rendering grow

### 2. Modular workbench implementation

Build a Vue 3 + Vite + Vue Router application with page containers, focused UI components, API services, and composables for task behavior.

Trade-off:

- Slightly more setup than a minimal page build
- Much better separation between transport, state synchronization, and rendering

### 3. Platform-style frontend foundation

Add a heavier app shell with Pinia, shared caching, and more generalized state architecture.

Trade-off:

- More future-proof in theory
- Unnecessary for the current product stage

### Chosen Direction

Approach 2 is approved.

It matches the current backend scope, keeps the codebase understandable, and leaves room for future features without introducing premature frontend infrastructure.

## Architecture

The frontend is a standalone application in `web/` that runs separately from the FastAPI backend during development.

### Frontend stack

- Vue 3
- Vite
- Vue Router
- TypeScript
- Vitest
- Vue Test Utils

### Application structure

- `web/src/main.ts`
  Application bootstrap
- `web/src/App.vue`
  App shell and top-level layout
- `web/src/router/`
  Route definitions
- `web/src/pages/`
  Route-level containers
- `web/src/components/`
  Reusable UI components
- `web/src/composables/`
  Task status, SSE, and result orchestration
- `web/src/services/`
  HTTP and SSE access wrappers
- `web/src/types/`
  Frontend contracts aligned to backend response models
- `web/src/assets/`
  Global styles and any local assets

The design intentionally avoids Pinia. Task state in this phase is local to the task detail flow, so composables are sufficient.

## Routing

The app uses a two-page structure:

### `/`

Repository submission page.

Responsibilities:

- Explain the product briefly
- Accept a GitHub repository URL
- Validate basic input presence on the client
- Submit analysis requests
- Navigate to the task page when submission succeeds

### `/tasks/:taskId`

Task workbench page.

Responsibilities:

- Load current task status
- Connect to the SSE event stream
- Fall back to status polling when needed
- Render progress, stage, and event history
- Load and display final analysis results when available
- Render failure states clearly when the task does not succeed

## Data Flow

### Submission flow

1. User enters a GitHub URL on `/`.
2. Frontend calls `POST /api/v1/analyze`.
3. On success, the frontend reads `task_id` from the response.
4. Frontend navigates to `/tasks/:taskId`.

### Task detail flow

1. On page load, fetch `GET /api/v1/tasks/{task_id}`.
2. Open `GET /api/v1/tasks/{task_id}/stream` as an SSE connection.
3. Append received events to a timeline in display order.
4. Update the current task status from event payloads when possible.
5. Run periodic status polling as a fallback when SSE is quiet or disconnected.
6. When task state becomes `succeeded`, fetch `GET /api/v1/tasks/{task_id}/result`.
7. If task state becomes `failed` or `cancelled`, stop result polling and render the failure summary.

### Result semantics

The frontend must follow backend contracts exactly:

- `200` with `AnalysisResult`: render the result sections
- `202`: show that the result is still being prepared
- `200` with terminal failure payload: show terminal error state
- `404`: show a task-not-found state

The frontend must not infer success without a successful result payload.

## UI Design

The interface should feel like a deliberate engineering tool rather than a default admin panel.

### Submission page

The submission page uses a hero-style workbench layout:

- Product title and short explanation
- One prominent URL input field
- One clear primary action
- Small supporting text describing public GitHub repository support

The page should feel focused and lightweight rather than dashboard-heavy.

### Task detail page

The task detail page has three primary sections:

#### 1. Task overview

Shows:

- Task ID
- State
- Current stage
- Progress value
- Current message or summary

#### 2. Event timeline

Shows:

- SSE event history in chronological order
- Stage progress in human-readable form
- Clear distinction between normal progress and error events

#### 3. Result panels

Shows:

- Project overview
- Detected tech stack
- Backend analysis
- Frontend analysis
- Core logic flows
- Beginner learning guide
- Markdown raw output

The Markdown section remains plain text or preformatted text in this phase. No Markdown renderer is required.

## Component Design

The frontend should use focused components with clear responsibilities.

Expected component set:

- `RepositorySubmitForm`
  GitHub URL entry and submit action
- `TaskStatusCard`
  State, stage, progress, and summary display
- `TaskEventTimeline`
  Ordered rendering of SSE events
- `ResultSectionCard`
  Reusable wrapper for result subsections
- `AnalysisResultView`
  Structured rendering of the final analysis payload
- `TaskErrorState`
  Task failure or not-found presentation

Page files should orchestrate these components rather than contain low-level HTTP and event handling directly.

## Service and Composable Design

### Services

`services/api.ts` should provide request helpers for:

- create analysis task
- fetch task status
- fetch task result

`services/stream.ts` should provide a small SSE wrapper that:

- opens a task stream
- emits parsed event payloads
- exposes close and error hooks

### Composables

`useTaskStatus`

- loads initial status
- manages polling fallback
- exposes current state and refresh controls

`useTaskStream`

- manages the SSE lifecycle
- appends timeline events
- exposes connection state

`useAnalysisResult`

- fetches result payloads
- handles `202`, failure, and success responses
- exposes loading, terminal, and resolved result state

These composables keep transport and state logic out of page templates.

## Error Handling

The frontend must distinguish these cases clearly:

- Invalid or missing GitHub URL before submission
- Request submission failure
- Task not found
- SSE disconnected but polling still active
- Task failed or cancelled
- Result not yet available
- Unexpected API response shape

Each case should produce direct, non-generic copy so the operator understands whether to retry, wait, or inspect the task.

## Responsive Behavior

The frontend must support desktop and mobile widths.

Desktop:

- Submit page centers the workbench
- Task detail page can use a split or stacked section layout depending on available width

Mobile:

- All sections stack vertically
- Inputs and controls remain full-width and touch-friendly
- Timeline cards avoid cramped horizontal layouts

## Testing Strategy

Implementation must follow TDD.

The minimum frontend test coverage for this phase is:

### Unit and component tests

- Submit form validation and disabled state
- Status card rendering by task state
- Event timeline rendering from received event items
- Result view rendering from a successful `AnalysisResult`
- Error state rendering for failed and missing tasks

### Page and flow tests

- Successful submit navigates from `/` to `/tasks/:taskId`
- Task page loads initial status on mount
- SSE event arrival updates the rendered timeline
- Succeeded task triggers result fetch and renders result sections
- Failed task shows terminal error UI

### Service tests

- API request wrappers map responses correctly
- Result loader handles `202`, `200`, and `404` cases
- SSE wrapper normalizes event payload parsing

## Delivery Boundaries

This phase modifies only the frontend application and supporting developer documentation needed to run it.

The frontend should consume the existing backend API contract without requiring backend endpoint changes.

Minor backend adjustments are acceptable only if a real integration mismatch is discovered during implementation, but that is not part of the intended scope.

## Risks and Mitigations

### Risk: SSE updates and status polling conflict

Mitigation:

- Treat SSE as the preferred live transport
- Keep polling as a fallback only
- Centralize status reconciliation in composables

### Risk: Result rendering becomes tightly coupled to raw backend payloads

Mitigation:

- Define explicit frontend types
- Keep rendering grouped by semantic section instead of direct JSON dumping

### Risk: Frontend grows into an unstructured dashboard

Mitigation:

- Keep the two-page route boundary strict
- Use focused section components
- Avoid adding unrelated controls in this phase

## Approval Record

Approved interactively in this session:

- Build the frontend now, after backend MVP completion
- Use Vue
- Frontend scope is a complete workbench rather than a one-page toy
- Use two pages: `/` and `/tasks/:taskId`
- Implement as a standalone app under `web/`
- No visual companion usage for design

## Implementation Readiness

This design is approved for conversion into a frontend implementation plan.
