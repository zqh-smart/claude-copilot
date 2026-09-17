# Frontend Design & Visual Aesthetic Skill

This skill guides the creation of distinctive, production-grade frontend interfaces for **Claude Copilot / frontend**.
It enforces strong design hierarchy, typography restraint, cohesive color palette, and polished component layout while avoiding generic "AI template" slop.

## Core Design Principles

### 1. Typography & Hierarchy
- Use bold, scannable headlines with proper weight contrast (`font-bold text-slate-900` vs `text-slate-500`).
- Keep technical labels and ID tags restrained (`font-mono text-xs text-slate-500` or rounded chips).
- Avoid wall-of-text paragraphs; break long outputs into structured sections, lists, or stat callouts.

### 2. Layout & Spacing
- **Poster Viewport**: Treat primary landing areas and headers as clean visual anchors.
- **Card Restraint**: Avoid unnecessary nested card-in-card "card soup". Use soft border dividers, subtle background fills (`bg-slate-50/50`), and generous whitespace (`gap-4`, `space-y-6`).
- **Asset Split Layout**: Use 2-column list + detail split for data-heavy inspection (Knowledge Base, Chat Memory).

### 3. Colors & Status Badges
- Primary Accent: Financial Emerald (`bg-emerald-800`, `text-emerald-800`, `border-emerald-200`).
- Surface: Clean Slate (`bg-white`, `bg-slate-50`, `border-slate-200/80`).
- Status Chips:
  - Success: `bg-emerald-100 text-emerald-800`
  - Warning: `bg-amber-100 text-amber-800`
  - Error: `bg-red-100 text-red-800`
  - Neutral / Info: `bg-slate-100 text-slate-700`

### 4. Motion & Micro-interactions
- Use subtle scale on hover (`hover:scale-102` / `hover:border-slate-300`).
- Include active/loading pulse indicators for background async jobs (`animate-pulse`).
- Ensure interactive buttons have explicit disabled and loading states.
