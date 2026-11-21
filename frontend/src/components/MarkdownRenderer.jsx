import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import MermaidViewer from './MermaidViewer';

export default function MarkdownRenderer({ content, onCitationClick }) {
  if (!content) return null;

  let cleanContent = typeof content === 'string' ? content : '';

  // Protect code blocks (including ```mermaid blocks) from citation regex transformations
  const parts = cleanContent.split(/(```[\s\S]*?```)/g);
  cleanContent = parts
    .map((part, index) => {
      // If inside a code block, leave completely untouched
      if (index % 2 === 1) {
        return part;
      }
      // Pull isolated citation lines inline with the preceding sentence
      let text = part.replace(
        /([^\n])\n{1,2}\s*\[\s*`?([a-zA-Z0-9_\-\.\/]+:\d+(?:[\-–‑]\d+)?)`?\s*\]/g,
        '$1 [$2](#cite)'
      );
      // Convert remaining bracket citations into citation link tokens
      text = text.replace(
        /\[\s*`?([a-zA-Z0-9_\-\.\/]+:\d+(?:[\-–‑]\d+)?)`?\s*\](?!\()/g,
        '[$1](#cite)'
      );
      return text;
    })
    .join('');

  return (
    <div className="md text-[#D4D4DA] leading-relaxed break-words font-sans">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, href, children, ...props }) => {
            if (href === '#cite') {
              const citText = String(children);
              return (
                <button
                  type="button"
                  onClick={() => onCitationClick?.(citText)}
                  className="inline-flex items-center text-[12px] font-mono font-medium text-[#4ADE80] bg-[#12261A] border border-[#1F5A38] rounded px-1.5 py-0.5 mx-1 cursor-pointer hover:bg-[#1a3825] hover:text-[#86EFAC] transition-colors align-baseline"
                  title="Click to view file source"
                >
                  {citText} ↗
                </button>
              );
            }
            // Internal anchor hash link
            if (href && href.startsWith('#')) {
              const targetId = href.slice(1);
              return (
                <a
                  href={href}
                  onClick={(e) => {
                    e.preventDefault();
                    const el = document.getElementById(targetId);
                    if (el) {
                      el.scrollIntoView({ behavior: 'smooth' });
                    }
                  }}
                  className="text-[#4ADE80] hover:text-[#86EFAC] hover:underline"
                >
                  {children}
                </a>
              );
            }
            return (
              <a
                {...props}
                href={href}
                className="text-[#4ADE80] hover:text-[#86EFAC] hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            );
          },
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-4 rounded-lg border border-[#26262C] bg-[#0A0A0B]">
              <table className="min-w-full divide-y divide-[#26262C] text-sm font-sans" {...props} />
            </div>
          ),
          thead: ({ node, ...props }) => (
            <thead className="bg-[#131316] text-[#ECECEE] font-semibold text-left" {...props} />
          ),
          th: ({ node, ...props }) => (
            <th className="px-3.5 py-2.5 font-semibold text-[#ECECEE] border-b border-[#26262C]" {...props} />
          ),
          td: ({ node, ...props }) => (
            <td className="px-3.5 py-2.5 border-t border-[#26262C] text-[#D4D4DA]" {...props} />
          ),
          code: ({ node, inline, className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            const codeString = String(children).replace(/\n$/, '');

            if (!inline && language === 'mermaid') {
              return (
                <div className="my-5">
                  <MermaidViewer chart={codeString} />
                </div>
              );
            }

            // Safeguard: Never render a citation as a code block
            const isCitation = /^[a-zA-Z0-9_\-\.\/]+:\d+(?:[\-–‑]\d+)?$/.test(codeString.trim());
            if (isCitation) {
              return (
                <button
                  type="button"
                  onClick={() => onCitationClick?.(codeString.trim())}
                  className="inline-flex items-center text-[12px] font-mono font-medium text-[#4ADE80] bg-[#12261A] border border-[#1F5A38] rounded px-1.5 py-0.5 mx-1 cursor-pointer hover:bg-[#1a3825] transition-colors"
                >
                  {codeString} ↗
                </button>
              );
            }

            // Proper detection of inline vs block code:
            // If it doesn't have multiple lines and doesn't specify a language block, render inline!
            const isBlock = Boolean(language) || codeString.includes('\n');

            if (!isBlock) {
              return (
                <code
                  className="bg-[#131316] text-[#4ADE80] px-1.5 py-0.5 rounded text-[13px] font-mono border border-[#2A2A30] mx-0.5 inline align-baseline"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <code
                className="block bg-[#0A0A0B] border border-[#232328] text-[#ECECEE] p-4 rounded-xl text-xs font-mono overflow-x-auto my-4"
                {...props}
              >
                {children}
              </code>
            );
          },
          h1: ({ node, ...props }) => (
            <h1 className="text-3xl font-bold tracking-tight text-[#ECECEE] pb-3 border-b border-[#26262C] my-4" {...props} />
          ),
          h2: ({ node, children, ...props }) => {
            const text = React.Children.toArray(children)
              .map((c) => (typeof c === 'string' ? c : c?.props?.children || ''))
              .join('');
            const slug = text
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, '-')
              .replace(/(^-|-$)/g, '');
            return (
              <h2
                id={slug}
                className="scroll-mt-8 text-xl font-semibold text-[#ECECEE] pb-2 border-b border-[#26262C] mt-8 mb-3"
                {...props}
              >
                {children}
              </h2>
            );
          },
          h3: ({ node, ...props }) => (
            <h3 className="text-lg font-semibold text-[#ECECEE] mt-6 mb-2" {...props} />
          ),
          p: ({ node, ...props }) => <p className="mb-3.5 last:mb-0 text-[#D4D4DA] text-base leading-relaxed" {...props} />,
          ul: ({ node, ...props }) => <ul className="list-disc pl-5 my-3 space-y-1.5 text-[#D4D4DA]" {...props} />,
          ol: ({ node, ...props }) => <ol className="list-decimal pl-5 my-3 space-y-1.5 text-[#D4D4DA]" {...props} />,
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="border border-[#1F5A38] bg-[#0E1A13] rounded-[10px] px-5 py-4 my-4 not-italic"
              style={{ borderLeft: '3px solid #4ADE80' }}
              {...props}
            />
          ),
          li: ({ node, ...props }) => <li className="text-base text-[#D4D4DA] leading-relaxed" {...props} />,
        }}
      >
        {cleanContent}
      </ReactMarkdown>
    </div>
  );
}
