# IntelliClaim AI — Frontend

React 19 + Vite frontend for the IntelliClaim AI insurance document intelligence platform.

## Stack

- React 19.2.7 + Vite 8
- React Router 7
- Recharts (analytics charts)
- Lucide React (icons)
- Axios (API client)

## Pages

| Route | Page | Description |
|---|---|---|
| `/` | Dashboard | Claims trend, risk breakdown, recent activity |
| `/documents` | Documents | Upload PDFs/images, view OCR results |
| `/claims` | Claims | CRUD, status management, filters |
| `/rag-search` | AI Search | Natural-language RAG query interface |
| `/validation` | Validation | Risk scores, fraud flags, AI review |

## Development

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # production build → dist/
```

## Environment

```env
VITE_API_URL=http://localhost:8000   # backend URL
```

For production, set `VITE_API_URL` to the Railway backend URL in Vercel's environment variables.

## Deployment

Deployed via Vercel. The root `vercel.json` configures the monorepo build:

```json
{
  "buildCommand": "cd frontend && npm install && npm run build",
  "outputDirectory": "frontend/dist"
}
```
