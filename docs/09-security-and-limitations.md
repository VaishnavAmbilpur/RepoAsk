# Security & Limitations

## Security Model

### Repository Access

- **Public repositories only.** The system uses `GIT_TERMINAL_PROMPT=0` to prevent interactive auth prompts. Private repositories will fail to clone with a clear error message.
- **Shallow clone (depth=1).** Only the latest commit is cloned. No git history is downloaded.
- **Temporary clone directory.** Cloned files are stored in the system temp directory and deleted after indexing. No repository files persist on disk beyond the database.

### Input Validation

- **GitHub URL parsing.** The URL is validated with a regex that extracts `owner/name`. Invalid URLs return a 400 error.
- **File size cap.** Files larger than 500 KB are skipped during indexing to prevent memory exhaustion.
- **Chunk cap.** Each repository is limited to 450 chunks to prevent embedding timeout.

### Output Sanitization

- **DOMPurify.** All rendered markdown is sanitized on the frontend before DOM insertion.
- **Citation verification.** File paths in LLM answers are verified against the database. Invalid paths are removed.
- **No code execution.** The system never runs code from indexed repositories.

### API Security

- **CORS whitelist.** Only configured origins can make requests to the API.
- **No authentication.** The API is currently open. This is intentional for a local development tool. For production, add an auth layer.
- **No rate limiting.** No request throttling is implemented. For production, add rate limiting at the reverse proxy level.

---

## Known Limitations

### Indexing

| Limitation | Detail |
|---|---|
| Public repos only | Private repositories cannot be cloned |
| 450 chunk cap | Large repositories lose coverage beyond this limit |
| No incremental updates | Re-indexing replaces all previous data |
| No branch selection | Always clones the default branch |
| Binary files skipped | Images, PDFs, compiled files are excluded |
| 500 KB file size limit | Large generated or minified files are skipped |

### Search & Retrieval

| Limitation | Detail |
|---|---|
| Brute-force similarity | No ANN index — works fine at 450 chunks, but would not scale to 100K+ |
| No keyword search | Only semantic (vector) search. Exact identifier search is not supported |
| No multi-hop retrieval | The system does not follow import chains across files |
| No conversation memory | Each question is independent — no follow-up context |

### Answer Quality

| Limitation | Detail |
|---|---|
| Free-tier models | Answer quality depends on the LLM model. Free models may produce less detailed answers |
| 12-second timeout | If the LLM does not respond in 12 seconds, the next model is tried |
| 1,600 token max | Long answers are truncated |
| No streaming generation | Tokens are streamed word-by-word after the full answer is generated |
| Hallucination possible | The LLM may describe behavior not present in the code, though citation verification catches file-level errors |

### Frontend

| Limitation | Detail |
|---|---|
| No persistent storage | Question history is lost on page refresh |
| No auth | Anyone with the URL can access the app |
| No mobile layout | The 3-column layout requires a desktop viewport |
| Right sidebar always visible | Only the left sidebar is collapsible |

