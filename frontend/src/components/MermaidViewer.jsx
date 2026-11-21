import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'loose',
  suppressErrorRendering: true,
  theme: 'dark',
  fontFamily: 'Inter, system-ui, sans-serif',
  themeVariables: {
    darkMode: true,
    background: '#0A0A0B',
    primaryColor: '#0E1A13',
    primaryTextColor: '#ECECEE',
    primaryBorderColor: '#4ADE80',
    lineColor: '#8B8B95',
    secondaryColor: '#131316',
    tertiaryColor: '#1A1A1F',
    edgeLabelBackground: '#131316',
  },
});

function sanitizeMermaidChart(rawChart) {
  if (!rawChart) return '';

  let lines = rawChart.trim().split('\n');
  let cleanLines = [];

  for (let line of lines) {
    let l = line.trim();
    if (!l) continue;

    // Remove markdown citation links
    l = l.replace(/\[\s*`?[a-zA-Z0-9_\-\.\/]+:\d+(?:[\-–‑]\d+)?`?\s*\](?:\(#cite\))?/g, '');
    l = l.replace(/\[\d+\]/g, '');

    // Ensure node labels with brackets like Node[Label with (stuff)] are quoted as Node["Label with (stuff)"]
    l = l.replace(/([a-zA-Z0-9_]+)\[([^"\]]+)\]/g, (match, id, text) => {
      return `${id}["${text.trim().replace(/"/g, "'")}"]`;
    });

    // Remove dangling arrows at end of line (often present while streaming)
    l = l.replace(/\s*(?:-->|---|-.->|-\.->|==>)\s*$/, '');

    if (l) {
      cleanLines.push(l);
    }
  }

  return cleanLines.join('\n');
}

export default function MermaidViewer({ chart }) {
  const containerRef = useRef(null);
  const [svgContent, setSvgContent] = useState('');
  const [renderError, setRenderError] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    let isMounted = true;
    if (!chart || !chart.trim()) return;

    const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
    const cleaned = sanitizeMermaidChart(chart);

    const cleanupStray = () => {
      const el = document.getElementById(id);
      if (el) el.remove();
      const errEl = document.getElementById(`d${id}`);
      if (errEl) errEl.remove();
      document.querySelectorAll(`[id^="dmermaid-"], [id^="mermaid-"]`).forEach((node) => {
        if (node.tagName.toLowerCase() === 'svg' && node.parentElement === document.body) {
          node.remove();
        } else if (node.parentElement === document.body && node.id.startsWith('dmermaid-')) {
          node.remove();
        }
      });
    };

    mermaid
      .parse(cleaned, { suppressErrors: true })
      .then((isValid) => {
        if (!isMounted) return;
        if (!isValid) return; // Incomplete chart during streaming

        return mermaid.render(id, cleaned).then(({ svg }) => {
          if (isMounted) {
            setSvgContent(svg);
            setRenderError(false);
          }
        });
      })
      .catch(() => {
        if (isMounted && !svgContent) {
          setRenderError(true);
        }
      })
      .finally(() => {
        cleanupStray();
      });

    return () => {
      isMounted = false;
      cleanupStray();
    };
  }, [chart]);

  // Handle Escape key for fullscreen modal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  if (renderError && !svgContent) {
    return (
      <div className="p-3 text-xs font-mono text-[#8B8B95] border border-[#232328] rounded-lg bg-[#0D0D0F]">
        Generating visual architecture graph...
      </div>
    );
  }

  return (
    <>
      <div className="relative group my-5">
        <div
          ref={containerRef}
          className="overflow-x-auto p-5 bg-[#0A0A0B] border border-[#232328] rounded-xl flex justify-center items-center [&>svg]:max-w-full [&>svg]:h-auto shadow-inner"
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
        {svgContent && (
          <button
            type="button"
            onClick={() => setIsFullscreen(true)}
            className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition-opacity text-xs font-medium text-[#A1A1AA] hover:text-[#ECECEE] bg-[#131316] hover:bg-[#1F1F24] border border-[#2A2A30] rounded-md px-2 py-1 flex items-center gap-1 cursor-pointer shadow-md"
            title="Expand diagram"
          >
            <span>Expand</span>
            <span>⛶</span>
          </button>
        )}
      </div>

      {/* Fullscreen Diagram Modal */}
      {isFullscreen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm">
          <div className="relative w-full max-w-6xl max-h-[90vh] bg-[#0A0A0B] border border-[#2A2A30] rounded-2xl flex flex-col p-6 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between pb-4 border-b border-[#1F1F24] mb-4">
              <span className="text-sm font-semibold text-[#ECECEE]">Visual Architecture Diagram</span>
              <button
                type="button"
                onClick={() => setIsFullscreen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-[#131316] hover:bg-[#1F1F24] text-[#A1A1AA] hover:text-[#ECECEE] border border-[#2A2A30] transition-colors cursor-pointer"
              >
                ✕
              </button>
            </div>
            <div
              className="flex-1 overflow-auto flex items-center justify-center p-4 [&>svg]:max-w-none [&>svg]:w-auto [&>svg]:min-w-[700px]"
              dangerouslySetInnerHTML={{ __html: svgContent }}
            />
          </div>
        </div>
      )}
    </>
  );
}
