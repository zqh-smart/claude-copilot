# Frontend boundaries

- Treat `apps/workbench` and `apps/chat-ui` as separate product applications.
- Keep financial workflows in the Vue 3/Vite workbench and complete conversational agent UX in the Next.js chat app.
- Never import React UI or LangGraph SDK domain types into the workbench.
- Put framework-neutral Claude Copilot DTOs in `packages/contracts`; each app owns its environment-variable adapter.
- Workbench streaming is limited to task/report progress over backend REST/SSE. Do not recreate full Agent Chat there.
- Keep development ports stable: workbench 3000, chat 3001, FastAPI 8000.
- Treat Yudao UI Admin Vue3 as a source of selected frontend practices only. Never add its Java/RuoYi backend protocols, permission APIs, or code-generation backend.
