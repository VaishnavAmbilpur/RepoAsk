const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
const API_BASE = `${BACKEND_URL}/api/v1`;

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!res.ok) {
    let msg = `HTTP error ${res.status}`;
    try {
      const errData = await res.json();
      msg = errData.detail || errData?.message || msg;
    } catch (_) {}
    throw new Error(msg);
  }

  return await res.json();
}

export const apiClient = {
  // List indexed repositories
  async listRepos() {
    return request('/repos');
  },

  // Index a new GitHub repository
  async indexRepo(url) {
    return request('/repos', {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  },

  // Get repository metadata
  async getRepo(repoId) {
    return request(`/repos/${repoId}`);
  },

  // Get file content for source viewer
  async getFile(repoId, path, start = 1, end = 0) {
    const params = new URLSearchParams({ path, start: String(start || 1), end: String(end || 0) });
    return request(`/repos/${repoId}/file?${params.toString()}`);
  },

  // Ask with SSE Stream (handling live stages: searching, connecting, checking, token, citation, done, error)
  askStream(repoId, question, conversationId, { onStatus, onToken, onCitation, onDone, onError }) {
    const controller = new AbortController();

    (async () => {
      try {
        const response = await fetch(`${API_BASE}/repos/${repoId}/ask`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, conversation_id: conversationId }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: 'Ask request failed' }));
          onError?.(err.detail || 'Ask request failed');
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';

          for (const block of lines) {
            if (!block.trim()) continue;
            let event = 'message';
            let dataStr = '';
            for (const line of block.split('\n')) {
              if (line.startsWith('event: ')) event = line.slice(7).trim();
              else if (line.startsWith('data: ')) dataStr = line.slice(6).trim();
            }

            if (!dataStr) continue;
            try {
              const parsed = JSON.parse(dataStr);
              if (event === 'status') onStatus?.(parsed);
              else if (event === 'token') onToken?.(parsed.text);
              else if (event === 'citation') onCitation?.(parsed);
              else if (event === 'done') onDone?.(parsed);
              else if (event === 'error') onError?.(parsed.message || 'Stream error');
            } catch (_) {}
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          onError?.(err.message || 'Network error occurred');
        }
      }
    })();

    return () => controller.abort();
  },
};
