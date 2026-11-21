# User Flow

## Overview

RepoAsk has 4 screens, presented in linear order the first time and freely navigable after that.

---

## Flow 1: Index a New Repository

### Screen 1 — Home (Paste Link)

**URL:** `/`

1. The user arrives at the home page.
2. The page shows a hero section: "Ask any GitHub repo anything."
3. Below the hero is an input bar with a GitHub icon and a green "Analyze repo" button.
4. The user pastes a public GitHub URL (e.g., `https://github.com/pallets/flask`).
5. The user clicks "Analyze repo" or presses Enter.

**Alternate paths:**
- If the repository was already indexed, the app shows it under "Recent / Samples" as a quick-launch pill. Clicking it goes directly to Screen 3.
- If the URL is invalid, an error banner appears below the input bar.
- Sample repositories (flask, express, fastapi) are shown as clickable pills for first-time users.

### Screen 2 — Reading the Repository

**URL:** `/` (same page, different state)

1. The page transitions to a centered progress card.
2. A 5-step checklist animates as the backend processes the repository:
   - ✅ Downloaded repository (shows file count)
   - ✅ Filtered non-code files
   - ⏳ Chunked code by language
   - ⏳ Generated embeddings
   - ⏳ Ready to answer
3. A progress bar fills from left to right.
4. A countdown timer shows estimated seconds remaining.
5. A "Cancel" button in the top-right lets the user abort.
6. When complete, the app navigates to `/repo/{repoId}`.

**Timing:** 15–45 seconds for typical repositories (under 500 files).

---

## Flow 2: Ask Questions

### Screen 3 — Empty Workspace

**URL:** `/repo/{repoId}`

1. The AnswerView loads with a 3-column layout.
2. The center column shows "What do you want to know?" with 3 suggestion chips:
   - "How does request routing work?"
   - "Where is configuration initialized?"
   - "What happens during application startup?"
3. The left sidebar shows default example questions.
4. The right sidebar shows placeholder text: "Sections will appear with answers."
5. A sticky input bar at the bottom lets the user type a question.

**Actions:**
- Type a question and press Enter or click "Ask" (Ctrl+Enter also works).
- Click a suggestion chip to auto-ask that question.
- Click "New repo" in the navbar to go back to Screen 1.

### Screen 4 — Thinking → Answer

**URL:** `/repo/{repoId}` (same page, different state)

**Phase A: Thinking (2–8 seconds)**

1. The center column shows the user's question at the top.
2. A status checklist animates:
   - ✅ Searched the repo — "Found {N} related files"
   - ✅ Followed connections between files
   - ⏳ Checking the answer — "Verifying each statement against GitHub"
3. Below the checklist, a skeleton shimmer card hints at the incoming document.
4. A "Stop" button lets the user cancel.

**Phase B: Answer Document**

1. The skeleton is replaced by a formatted document card:
   - **Question label** at the top
   - **H1 title** (auto-generated from the answer)
   - **Short answer callout** (green-bordered box)
   - **Body sections** with H2 headings, paragraphs, bullets, tables
   - **Mermaid diagrams** rendered inline (when the question is about a flow or process)
2. A toolbar above the card offers:
   - Preview / Markdown toggle
   - Copy .md button
   - Download .md button
3. Follow-up suggestion chips appear below the document.

**Sidebar updates:**
- **Left sidebar:** The question appears in the history list. The active question is highlighted green.
- **Right sidebar:** "On this page" shows clickable H2 headings. "Sources on GitHub" lists verified file paths with links to open them in a preview modal or on GitHub.

---

## Flow 3: Browse History

1. Click any earlier question in the left sidebar.
2. The center column loads that question's saved answer, citations, and TOC.
3. The active history item highlights with a green left border.
4. Click "New question" (green button) to clear the view and start fresh.

---

## Flow 4: View Source Files

1. Click any file path in the right sidebar "Sources on GitHub" section.
2. A modal opens showing the file's source code with line numbers.
3. The relevant lines (from the citation) are highlighted.
4. An external link icon opens the file on GitHub in a new tab.
5. Click outside the modal or press Escape to close.

---

## Sidebar Toggle

- The left sidebar can be collapsed and expanded using a toggle button in the navbar.
- When collapsed, the center column expands to fill the space.
- The toggle icon switches between `PanelLeftClose` (when open) and `PanelLeftOpen` (when closed).

---

## Navigation Map

```
/                          → HomeView (Screen 1 or 2)
/repo/{repoId}             → AnswerView (Screen 3 or 4)
/repo/{repoId}/ask         → Redirects to /repo/{repoId}
/repo/{repoId}/*           → Redirects to /repo/{repoId}
/*                         → Redirects to /
```

