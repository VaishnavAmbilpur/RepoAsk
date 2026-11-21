# Idea & Solution

## The Problem

Developers spend a large part of their time reading code, not writing it. When they open a new GitHub repository, they face thousands of files, nested folders, and no clear entry point. They must jump between files, follow imports, and build a mental model of the system before they can answer even basic questions like "how does this work?" or "where is the database set up?"

Existing tools do not solve this:
- **GitHub search** finds files and symbols, but does not explain how they connect.
- **README files** go stale and cover only the surface.
- **ChatGPT / Copilot** do not have the full codebase context and hallucinate file names and line numbers.

## The Solution — RepoAsk

RepoAsk lets a user paste any public GitHub URL and ask questions about the repository in plain English. It returns short, structured answers as documents — with verified file citations, diagrams, and a table of contents.

### How It Works (High Level)

1. **Paste a link** → RepoAsk shallow-clones the repository.
2. **Automatic indexing** → The system filters non-code files, splits code into language-aware chunks using AST splitters, and generates vector embeddings in-process.
3. **Ask anything** → The user types a question. A LangGraph RAG pipeline retrieves relevant chunks, synthesizes a plain-English answer, and verifies every citation against the actual codebase.
4. **Read the answer** → The user sees a formatted document with headings, a short answer callout, Mermaid diagrams (when helpful), and clickable source file links.

### Core Value Propositions

| Value | How It Is Delivered |
|---|---|
| **Plain-language answers** | ASD-STE100 Simplified Technical English constraints in the system prompt |
| **Diagrams when they help** | Mermaid flowcharts for processes, tables for structured data |
| **Checked against the repo** | Every statement verified against actual file paths and line numbers before display |
| **No code to read** | The LLM is instructed to never show code blocks or snippets |

### What Makes This Different

- **Grounded or silent.** If the answer cannot be verified against the repository, the system says so instead of guessing.
- **Structured output.** Every answer follows a consistent document format: title → short answer → sections → sources.
- **Local-first.** Embeddings run in-process with FastEmbed. The database is a local SQLite file. The only external call is to the LLM via OpenRouter.
- **Free to run.** The default LLM model is a free-tier model on OpenRouter. No credit card needed.

## Target Users

1. **Developers exploring unfamiliar codebases** — joining a new team, evaluating open-source libraries, or doing code reviews.
2. **Students and learners** — understanding how real-world projects are structured.
3. **Technical writers** — gathering information about a codebase for documentation.

## Success Metrics

| Metric | Target |
|---|---|
| Time to first answer | Under 60 seconds from paste to answer |
| Citation accuracy | 100% of displayed sources exist in the repository |
| Answer relevance | User does not need to rephrase the question |
| Indexing coverage | Support for Python, JavaScript, TypeScript, Go, Rust, Java, C/C++ |

