import React, { useEffect, useState } from 'react';
import { apiClient } from '@/api/client';

export default function FileViewerModal({ repoId, citation, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!citation || !repoId) return;

    let path = citation.path;
    let start = citation.start_line || 1;
    let end = citation.end_line || 0;

    // Handle string citation like "src/app.py:10-25"
    if (typeof citation === 'string') {
      const match = citation.match(/^([^:]+)(?::(\d+)(?:-(\d+))?)?$/);
      if (match) {
        path = match[1];
        start = parseInt(match[2] || '1', 10);
        end = parseInt(match[3] || String(start + 20), 10);
      } else {
        path = citation;
      }
    }

    setLoading(true);
    setError(null);

    apiClient
      .getFile(repoId, path, Math.max(1, start - 15), end ? end + 20 : 0)
      .then((res) => {
        setData({
          path,
          start,
          end,
          lines: res.lines || [],
        });
      })
      .catch((err) => {
        setError(err.message || 'Failed to load file');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [repoId, citation]);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!citation) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs">
      <div className="card w-full max-w-4xl max-h-[85vh] flex flex-col p-0 overflow-hidden shadow-2xl border border-[#2A2A30] bg-[#101013]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#1F1F24] bg-[#0D0D0F]">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm font-semibold text-[#ECECEE]">
              {data?.path || (typeof citation === 'string' ? citation : citation.path)}
            </span>
            {data?.start && (
              <span className="text-xs font-mono text-[#4ADE80] bg-[#12261A] border border-[#1F5A38] px-2 py-0.5 rounded">
                Lines {data.start} - {data.end || data.start}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {data?.path && (
              <a
                href={`https://github.com/${repoId}/blob/main/${data.path}${data.start ? `#L${data.start}-L${data.end || data.start}` : ''}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-[#4ADE80] hover:text-[#86EFAC] hover:underline"
              >
                Open on GitHub ↗
              </a>
            )}
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-[#1B1B20] text-[#8B8B95] hover:text-[#ECECEE] transition-colors cursor-pointer"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-5 bg-[#0A0A0B]">
          {loading && (
            <div className="flex items-center justify-center py-16 text-[#8B8B95]">
              Loading source file...
            </div>
          )}

          {error && (
            <div className="p-4 text-sm text-[#F87171] bg-[#2A1315] border border-[#F87171]/40 rounded-lg">
              {error}
            </div>
          )}

          {!loading && !error && data?.lines && (
            <table className="w-full border-collapse">
              <tbody>
                {data.lines.map((l) => {
                  const isHighlighted =
                    data.start && data.end
                      ? l.n >= data.start && l.n <= data.end
                      : l.n === data.start;

                  return (
                    <tr
                      key={l.n}
                      className={
                        isHighlighted
                          ? 'bg-[#16231B] text-[#ECECEE]'
                          : 'hover:bg-[#131316] text-[#B4B4BC]'
                      }
                    >
                      <td className="w-12 pr-4 text-right select-none text-[#6B6B75] align-top">
                        {l.n}
                      </td>
                      <td className="whitespace-pre overflow-x-auto align-top text-[#D4D4DA]">
                        {l.text || ' '}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

