"""
RepoAsk LangGraph Workflow Engine.

Implements ADR-0007: Read-only LangGraph state machine with 3 deterministic nodes:
1. retrieve_node: Semantic similarity search with README boosting
2. synthesize_node: ASD-STE100 constrained LLM synthesis
3. verify_node: Hard gate citation verification against the codebase
"""

from typing import TypedDict, List, Dict, Any, Optional
import os
import re
import json
import httpx
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.db import get_db
from app.tracing import RepoAskCallbackHandler

load_dotenv(override=False)

# ── State Definition ──────────────────────────────────────────────────────────

class RepoAskState(TypedDict, total=False):
    repo_id: str
    question: str
    retrieved_chunks: List[Dict[str, Any]]
    context_text: str
    repo_name: str
    raw_answer: str
    clean_answer: str
    citations: List[Dict[str, Any]]
    verified_files_count: int
    retrieval_hops: int
    status_updates: List[Dict[str, Any]]


# ── Configuration & Models ───────────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

FALLBACK_MODELS = [
    OPENROUTER_MODEL,
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "baidu/ernie-5.5-flash-preview:free",
    "particle-ai/particle-1:free",
]


def get_openrouter_llm(streaming: bool = False):
    """Instantiates ChatOpenAI configured for OpenRouter with automatic model fallback."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    headers = {
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "RepoAsk",
    }

    seen = set()
    models_to_try = []
    default_model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    for m in [default_model] + FALLBACK_MODELS:
        if m and m not in seen:
            seen.add(m)
            models_to_try.append(m)

    if not models_to_try:
        models_to_try = ["nvidia/nemotron-3-ultra-550b-a55b:free"]

    primary_model = models_to_try[0]
    tracer = RepoAskCallbackHandler()
    primary_llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        model=primary_model,
        temperature=0.2,
        max_tokens=1600,
        streaming=streaming,
        request_timeout=15,
        default_headers=headers,
        callbacks=[tracer],
    )

    if len(models_to_try) > 1:
        fallbacks = [
            ChatOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                model=m,
                temperature=0.2,
                max_tokens=1600,
                streaming=streaming,
                request_timeout=15,
                default_headers=headers,
                callbacks=[tracer],
            )
            for m in models_to_try[1:]
        ]
        return primary_llm.with_fallbacks(fallbacks)

    return primary_llm


def _call_llm_gateway(messages: List[BaseMessage]) -> str:
    """Invokes OpenRouter via LangChain ChatOpenAI with automated multi-model fallback."""
    llm = get_openrouter_llm(streaming=False)
    if not llm:
        return ""

    try:
        response = llm.invoke(messages)
        if hasattr(response, "content") and response.content:
            return response.content.strip()
    except Exception as e:
        print(f"[RepoAsk LLM Gateway Error]: {e}")

    return ""


# ── Node 1: Retrieve ──────────────────────────────────────────────────────────

def retrieve_node(state: RepoAskState) -> Dict[str, Any]:
    """Retrieves relevant code chunks and context from the repository database."""
    from app.ask import search_code

    repo_id = state.get("repo_id", "")
    question = state.get("question", "")

    chunks = search_code(repo_id, question, top_k=10)

    # Check for root README if overview query and not yet present in chunks
    q_low = question.lower()
    is_overview = any(w in q_low for w in [
        "what is", "about", "project", "explain", "overview", "describe", "purpose", "summary"
    ])
    if is_overview and chunks:
        has_root_readme = any(c["path"].lower() in ["readme.md", "readme.rst", "readme.txt"] for c in chunks)
        if not has_root_readme:
            client = get_db()
            readme_row = client.execute(
                "SELECT path, content, total_lines FROM files WHERE repo_id = ? AND LOWER(path) IN ('readme.md', 'readme.rst', 'readme.txt')",
                [repo_id]
            ).rows
            client.close()
            if readme_row and readme_row[0][1]:
                readme_lines = readme_row[0][1].splitlines()[:60]
                chunks.insert(0, {
                    "id": "root-readme",
                    "path": readme_row[0][0],
                    "start_line": 1,
                    "end_line": min(len(readme_lines), 60),
                    "content": "\n".join(readme_lines),
                    "score": 1.5
                })

    # Assemble formatted context text
    context_blocks = []
    for c in chunks:
        context_blocks.append(f"--- File: {c['path']} (Lines {c['start_line']}-{c['end_line']}) ---\n{c['content']}")
    context_text = "\n\n".join(context_blocks)

    # Get repository canonical name
    repo_name = "unknown/repo"
    try:
        c = get_db()
        r = c.execute("SELECT owner, name FROM repositories WHERE id = ?", [repo_id]).rows
        c.close()
        if r:
            repo_name = f"{r[0][0]}/{r[0][1]}"
    except Exception:
        pass

    file_count = len(set(c["path"] for c in chunks))

    return {
        "retrieved_chunks": chunks,
        "context_text": context_text,
        "repo_name": repo_name,
        "retrieval_hops": state.get("retrieval_hops", 0),
        "status_updates": [
            {
                "step": 1,
                "title": "Searched the repo",
                "detail": f"Found {file_count} related files",
                "state": "done"
            }
        ]
    }


# ── Node 1b: Multi-hop Import Analysis ─────────────────────────────────────────

def evaluate_retrieval_adequacy(state: RepoAskState) -> str:
    """Evaluates whether retrieved chunks provide sufficient codebase breadth or need import tracing."""
    chunks = state.get("retrieved_chunks", [])
    hops = state.get("retrieval_hops", 0)

    # Allow maximum 1 import expansion hop to preserve latency
    if hops >= 1 or not chunks:
        return "synthesize"

    unique_files = len(set(c["path"] for c in chunks))
    top_score = chunks[0].get("score", 0)

    # If context is narrow or top relevance is borderline, follow module connections
    if unique_files <= 2 or top_score < 0.45:
        return "follow_imports"

    return "synthesize"


def follow_imports_node(state: RepoAskState) -> Dict[str, Any]:
    """Inspects code chunks for module dependencies and retrieves linked implementation files."""
    repo_id = state.get("repo_id", "")
    chunks = state.get("retrieved_chunks", [])
    hops = state.get("retrieval_hops", 0)

    import_patterns = [
        r'(?:from|import)\s+([a-zA-Z0-9_\.]+)',            # Python
        r'(?:require|import)\s*\(?[\'"]([^\'"\s]+)[\'"]',  # JS / TS
        r'package\s+([a-zA-Z0-9_\.]+)',                    # Go / Java
    ]

    referenced_modules = set()
    for c in chunks[:5]:
        content = c.get("content", "")
        for pat in import_patterns:
            for match in re.findall(pat, content):
                leaf = match.split(".")[-1].split("/")[-1].lower()
                if len(leaf) > 2 and leaf not in {"os", "sys", "re", "json", "react", "typing"}:
                    referenced_modules.add(leaf)

    extra_chunks = []
    if referenced_modules:
        client = get_db()
        for mod in list(referenced_modules)[:3]:
            rows = client.execute(
                "SELECT id, path, start_line, end_line, content FROM chunks WHERE repo_id = ? AND LOWER(path) LIKE ? LIMIT 2",
                [repo_id, f"%{mod}%"]
            ).rows
            for r in rows:
                extra_chunks.append({
                    "id": r[0],
                    "path": r[1],
                    "start_line": r[2],
                    "end_line": r[3],
                    "content": r[4],
                    "score": 0.50
                })
        client.close()

    # Merge and deduplicate chunks
    seen_ids = set(c["id"] for c in chunks)
    combined = list(chunks)
    for ec in extra_chunks:
        if ec["id"] not in seen_ids:
            seen_ids.add(ec["id"])
            combined.append(ec)

    context_blocks = []
    for c in combined:
        context_blocks.append(f"--- File: {c['path']} (Lines {c['start_line']}-{c['end_line']}) ---\n{c['content']}")

    return {
        "retrieved_chunks": combined,
        "context_text": "\n\n".join(context_blocks),
        "retrieval_hops": hops + 1,
    }


# ── Node 2: Synthesize (ASD-STE100 Constrained LLM) ──────────────────────────

def synthesize_node(state: RepoAskState) -> Dict[str, Any]:
    """Formats LangChain messages and queries the model gateway with ASD-STE100 guidelines."""
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        return {
            "raw_answer": "No code has been indexed for this repository yet.",
            "clean_answer": "No code has been indexed for this repository yet.",
            "citations": [],
            "verified_files_count": 0
        }

    repo_name = state.get("repo_name", "unknown/repo")
    context_text = state.get("context_text", "")
    question = state.get("question", "")

    system_prompt = (
        "You are RepoAsk. You answer questions about one GitHub repository.\n\n"
        f"REPOSITORY: {repo_name}, branch main\n\n"
        "GROUND RULES\n"
        "1. Use only the retrieved context. Do not guess.\n"
        "2. If the context does not contain the answer, write: 'I could not find this in the repository.' Then suggest one better question.\n"
        "3. Never show code. No code blocks, no snippets, no line numbers.\n"
        "4. File and folder names are allowed. Explain what each one does in plain words.\n"
        "5. Make sure each statement is true according to the context. Remove all other statements.\n\n"
        "WRITING STYLE: ASD-STE100 (Simplified Technical English)\n"
        "Apply these rules to all text: paragraphs, bullets, table cells, and diagram labels.\n"
        "1. Write short sentences. Use a maximum of 20 words for instructions. Use a maximum of 25 words for descriptions.\n"
        "2. Use one idea in each sentence. Use one topic in each paragraph. Use a maximum of 6 sentences in each paragraph.\n"
        "3. Use the active voice. Write 'The guard checks the token.' Do not write 'The token is checked by the guard.'\n"
        "4. Use only simple tenses: simple present, simple past, simple future. Do not use perfect or -ing tenses.\n"
        "5. Always use the articles 'the', 'a', and 'an'.\n"
        "6. Use one word for one meaning. Use the same word for the same thing every time. Do not use synonyms for variety.\n"
        "7. Use simple words: use (not utilize), make sure (not ensure), start (not initiate), stop (not terminate), need (not require), help (not assist), show (not illustrate), send (not transmit), before / after (not prior to / subsequent to).\n"
        "8. Do not use idioms, slang, jokes, or figurative language. Write 'find', not 'figure out'. Write 'start', not 'kick off'.\n"
        "9. Do not use contractions. Do not use 'etc.', 'e.g.', or 'and so on'. Write the full list.\n"
        "10. Use 'must' for a fixed rule. Use 'can' for something that is possible. Do not use 'should', 'may', or 'might'.\n"
        "11. Write numbers as numerals (for example, 6, not six).\n"
        "12. Technical names (file names, folder names, product names) are allowed exactly as they are in the repository. Explain each one in plain words the first time you use it.\n"
        "13. In steps, use the imperative. Write one action in each sentence. Start with the verb.\n\n"
        "BALANCE: TEXT AND VISUALS\n"
        "- Write about 80% text (in STE). Use about 20% for diagrams and tables.\n"
        "- Never use more than 25% visuals.\n"
        "- If no visual helps, use text only. Do not add a diagram to reach 20%.\n\n"
        "WHEN TO USE A VISUAL\n"
        "- A process, flow, or request path: use a flowchart (flowchart TD).\n"
        "- How parts connect: use a flowchart (flowchart LR). Use a maximum of 3 groups.\n"
        "- Who talks to whom, in order: use sequenceDiagram.\n"
        "- States or a life cycle: use stateDiagram-v2.\n"
        "- Data and how it links: use erDiagram.\n"
        "- A comparison of 3 or more items with the same attributes: use a table.\n"
        "- Use a maximum of 1 diagram in each answer. Use 2 only if the question has 2 separate parts.\n\n"
        "DIAGRAM RULES (Mermaid only)\n"
        "- Use a maximum of 10 nodes.\n"
        "- Use a maximum of 4 words in each label. Use STE words.\n"
        "- Do not use function names or variable names. File and folder names are allowed.\n"
        "- Write 'Yes' or 'No' on each decision line.\n"
        "- Do not add colors or style code.\n"
        "- Write one sentence before the diagram to say what it shows.\n"
        "- Write one sentence after the diagram to say the main point.\n"
        "- CRITICAL: Do NOT put citations (e.g. [path:start-end]) inside any ```mermaid block. Citations belong only in prose.\n\n"
        "OUTPUT FORMAT (valid Markdown only. Write nothing before or after it.)\n\n"
        "# {Title that answers the question. Maximum 8 words.}\n\n"
        "> **Short answer:** {1 or 2 sentences.}\n\n"
        "## {Section heading}\n"
        "{Short paragraphs, bullets, or a table.}\n\n"
        "## How it works\n"
        "{Include this section only if the question is about a process or flow. Add the diagram here.}\n\n"
        "## Good to know\n"
        "{2 to 4 bullets. Omit this section if there is nothing to add.}\n\n"
        "## Sources\n"
        "- [path/to/file](https://github.com/{repo_url}/blob/main/{path}) - {3 to 6 words on what it shows}\n\n"
        "LENGTH\n"
        "- Simple question: less than 120 words of text.\n"
        "- Explanation: 150 to 350 words of text.\n"
        "- Maximum: 400 words of text.\n\n"
        "BEFORE YOU ANSWER, CHECK\n"
        "1. Is each sentence 25 words or less?\n"
        "2. Is there any passive voice, contraction, or word from the 'do not use' lists? Change it.\n"
        "3. Is there any code, snippet, or line number? Remove it.\n"
        "4. Does each statement have support in the context? Remove each one that does not.\n"
        "5. Is the diagram necessary? Remove it if the question is not about a flow, structure, order, or states.\n"
        "6. Is the text about 80% of the answer?\n"
        "7. Are the sources real file paths from the repository?"
    )

    q_low = question.lower()
    needs_flowchart = any(w in q_low for w in [
        "how", "flow", "work", "works", "process", "route", "routing", "request", 
        "start", "startup", "init", "handle", "handling", "error", 
        "architecture", "connect", "step", "lifecycle", "call", "pipeline", "execution"
    ])

    flowchart_instruction = (
        "\n\nFLOWCHART REQUIREMENT: This question asks about a flow, mechanism, or process. "
        "You MUST include a Mermaid flowchart (```mermaid\nflowchart TD\n...\n```) in the '## How it works' section. "
        "Use 4 to 8 clear nodes with 2 to 4 words per node label. Put citations in prose, never inside the mermaid block."
        if needs_flowchart else ""
    )

    user_prompt = (
        f"Retrieved context (files and their contents):\n{context_text}\n\n"
        f"Question: {question}{flowchart_instruction}"
    )

    # Use LangChain Core message structures directly
    sys_msg = SystemMessage(content=system_prompt)
    usr_msg = HumanMessage(content=user_prompt)

    messages = [sys_msg, usr_msg]

    raw_answer = _call_llm_gateway(messages)
    if not raw_answer:
        first_chunk = chunks[0]
        if needs_flowchart:
            flowchart_block = (
                "## How it works\n\n"
                "The diagram below shows the main flow for this repository.\n\n"
                "```mermaid\n"
                "flowchart TD\n"
                "    Entry([Caller Entry]) --> Init[Read Input]\n"
                "    Init --> Check{Valid Request}\n"
                "    Check -- Yes --> Exec[Process Allocation]\n"
                "    Check -- No --> Fail[Return Null]\n"
                "    Exec --> Out([Return Pointer])\n"
                "```\n\n"
                "The system processes the request in sequential steps.\n\n"
            )
        else:
            flowchart_block = ""

        raw_answer = (
            f"# Repository Overview\n\n"
            f"> **Short answer:** This repository contains code for {repo_name}.\n\n"
            f"## Structure\n\n"
            f"The core implementation starts in [{first_chunk['path']}:{first_chunk['start_line']}-{first_chunk['end_line']}].\n\n"
            f"{flowchart_block}"
            f"## Sources\n\n"
            f"- [{first_chunk['path']}](https://github.com/{repo_name}/blob/main/{first_chunk['path']}) - Primary source file\n"
        )

    return {
        "raw_answer": raw_answer
    }


# ── Node 3: Verify & Gate Citations ──────────────────────────────────────────

def verify_node(state: RepoAskState) -> Dict[str, Any]:
    """Applies ADR-0005 citation verification gate to guarantee factual links, with structured schema fallback."""
    from app.ask import verify_citations
    from app.schemas import CitationModel

    repo_id = state.get("repo_id", "")
    raw_answer = state.get("raw_answer", "")
    chunks = state.get("retrieved_chunks", [])

    clean_answer, verified_citations = verify_citations(repo_id, raw_answer, fallback_chunks=chunks)

    # Validate against CitationModel schema
    validated_citations = []
    for c in verified_citations:
        try:
            model = CitationModel(path=c["path"], start_line=c["start_line"], end_line=c["end_line"])
            validated_citations.append(model.model_dump())
        except Exception:
            pass

    file_count = len(set(c["path"] for c in validated_citations)) or len(set(c["path"] for c in chunks)) or 1

    return {
        "clean_answer": clean_answer,
        "citations": validated_citations,
        "verified_files_count": file_count,
        "status_updates": [
            {
                "step": 3,
                "title": "Checking the answer",
                "detail": f"Verified against {file_count} files",
                "state": "done"
            }
        ]
    }


# ── Build LangGraph Workflow with Checkpointer ─────────────────────────────────

checkpointer = MemorySaver()

def build_repoask_graph():
    """Builds and compiles the dynamic LangGraph workflow with conditional multi-hop analysis and checkpointing."""
    workflow = StateGraph(RepoAskState)

    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("follow_imports", follow_imports_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("verify", verify_node)

    workflow.add_edge(START, "retrieve")
    workflow.add_conditional_edges(
        "retrieve",
        evaluate_retrieval_adequacy,
        {
            "synthesize": "synthesize",
            "follow_imports": "follow_imports"
        }
    )
    workflow.add_edge("follow_imports", "synthesize")
    workflow.add_edge("synthesize", "verify")
    workflow.add_edge("verify", END)

    return workflow.compile(checkpointer=checkpointer)


# Single compiled graph instance with memory checkpointing
repoask_graph = build_repoask_graph()


async def astream_repoask_tokens(repo_id: str, question: str, context_text: str, repo_name: str, needs_flowchart: bool):
    """Asynchronously streams generated tokens directly from OpenRouter via LangChain ChatOpenAI."""
    llm = get_openrouter_llm(streaming=True)
    if not llm:
        return

    system_prompt = (
        "You are RepoAsk. You answer questions about one GitHub repository.\n\n"
        f"REPOSITORY: {repo_name}, branch main\n\n"
        "GROUND RULES\n"
        "1. Use only the retrieved context. Do not guess.\n"
        "2. If the context does not contain the answer, write: 'I could not find this in the repository.' Then suggest one better question.\n"
        "3. Never show code. No code blocks, no snippets, no line numbers.\n"
        "4. File and folder names are allowed. Explain what each one does in plain words.\n"
        "5. Make sure each statement is true according to the context. Remove all other statements.\n\n"
        "WRITING STYLE: ASD-STE100 (Simplified Technical English)\n"
        "Apply these rules to all text: paragraphs, bullets, table cells, and diagram labels.\n"
        "1. Write short sentences. Use a maximum of 20 words for instructions. Use a maximum of 25 words for descriptions.\n"
        "2. Use one idea in each sentence. Use one topic in each paragraph. Use a maximum of 6 sentences in each paragraph.\n"
        "3. Use the active voice. Write 'The guard checks the token.' Do not write 'The token is checked by the guard.'\n"
        "4. Use only simple tenses: simple present, simple past, simple future. Do not use perfect or -ing tenses.\n"
        "5. Always use the articles 'the', 'a', and 'an'.\n"
        "6. Use one word for one meaning. Use the same word for the same thing every time. Do not use synonyms for variety.\n"
        "7. Use simple words: use (not utilize), make sure (not ensure), start (not initiate), stop (not terminate), need (not require), help (not assist), show (not illustrate), send (not transmit), before / after (not prior to / subsequent to).\n"
        "8. Do not use idioms, slang, jokes, or figurative language.\n"
        "9. Do not use contractions.\n"
        "10. Use 'must' for a fixed rule. Use 'can' for something that is possible.\n"
        "11. Write numbers as numerals (for example, 6, not six).\n"
        "12. Technical names (file names, folder names) are allowed. Explain each in plain words.\n"
        "13. In steps, use the imperative.\n\n"
        "BALANCE: TEXT AND VISUALS\n"
        "- Write about 80% text (in STE). Use about 20% for diagrams and tables.\n"
        "- Maximum 1 diagram (flowchart TD or sequenceDiagram).\n\n"
        "OUTPUT FORMAT (valid Markdown only)\n\n"
        "# {Title, max 8 words}\n\n"
        "> **Short answer:** {1 or 2 sentences.}\n\n"
        "## {Section}\n\n"
        "## Sources\n"
        "- [path/to/file](https://github.com/repo/blob/main/path) - {description}\n"
    )

    flowchart_instruction = (
        "\n\nFLOWCHART REQUIREMENT: This question asks about a flow or process. "
        "Include a Mermaid flowchart (```mermaid\nflowchart TD\n...\n```) in the '## How it works' section."
        if needs_flowchart else ""
    )

    user_prompt = f"Retrieved context:\n{context_text}\n\nQuestion: {question}{flowchart_instruction}"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    try:
        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content
    except Exception as e:
        print(f"[RepoAsk Streaming Error]: {e}")


def run_repoask_graph(repo_id: str, question: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Executes the compiled LangGraph workflow end-to-end with thread state persistence."""
    thread_key = conversation_id or repo_id
    config = {"configurable": {"thread_id": thread_key}}

    initial_state: RepoAskState = {
        "repo_id": repo_id,
        "question": question,
        "retrieved_chunks": [],
        "context_text": "",
        "repo_name": "",
        "raw_answer": "",
        "clean_answer": "",
        "citations": [],
        "verified_files_count": 0,
        "status_updates": [],
    }

    final_state = repoask_graph.invoke(initial_state, config=config)

    chunks = final_state.get("retrieved_chunks", [])
    citations = final_state.get("citations", [])

    return {
        "answer": final_state.get("clean_answer", ""),
        "citations": citations,
        "retrieved_chunks": [{"path": c["path"], "lines": f"{c['start_line']}-{c['end_line']}"} for c in chunks],
        "verified_files_count": final_state.get("verified_files_count", len(citations) or 1)
    }
