import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Plus, Check, Copy, Download, ArrowUpRight, FileText, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { apiClient } from '@/api/client';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import FileViewerModal from '@/components/FileViewerModal';

// ─── SVG Icons ───────────────────────────────────────────────────────────────
function CheckCircle() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#4ADE80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-none">
      <circle cx="12" cy="12" r="10" />
      <path d="M8 12.5l2.5 2.5L16 9.5" />
    </svg>
  );
}
function SpinCircle() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" strokeWidth="2.5" strokeLinecap="round" className="flex-none animate-spin">
      <circle cx="12" cy="12" r="10" stroke="#26262C" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="#4ADE80" />
    </svg>
  );
}

// ─── Slug Generator for Table of Contents ───────────────────────────────────
function getSlug(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

// ─── Parse answer markdown into { title, shortAnswer, body, sources } ────────
function parseAnswer(md) {
  if (!md) return { title: 'Overview', shortAnswer: '', body: '', sources: [] };

  let title = 'Overview';
  let shortAnswer = '';
  let sources = [];
  let body = md;

  // Extract H1 title
  const h1 = md.match(/^#\s+(.+)$/m);
  if (h1) {
    title = h1[1].trim();
    body = body.replace(/^#\s+.+$/m, '').trimStart();
  }

  // Extract blockquote short answer  "> **Short answer:** ..."
  const bq = body.match(/^>\s*\*\*Short answer:\*\*\s*([\s\S]*?)(?=\n\n|\n##|$)/m);
  if (bq) {
    shortAnswer = bq[1].replace(/^>\s*/gm, '').trim();
    body = body.replace(/^>\s*\*\*Short answer:\*\*[\s\S]*?(?=\n\n|\n##|$)/m, '').trimStart();
  }

  // Also handle legacy "## Executive Summary" format
  if (!shortAnswer) {
    const exec = body.match(/^##\s+Executive Summary\s*\n+([\s\S]*?)(?=\n##|\n#|$)/im);
    if (exec) {
      shortAnswer = exec[1].trim();
      body = body.replace(/^##\s+Executive Summary\s*\n+[\s\S]*?(?=\n##|\n#|$)/im, '').trimStart();
    }
  }

  // Extract ## Sources section to deduplicate from body
  const srcSection = body.match(/^##\s+Sources\s*\n+([\s\S]*)$/im);
  if (srcSection) {
    const srcLines = srcSection[1].match(/^\s*-\s+\[(.+?)\]/gm) || [];
    sources = srcLines.map((l) => {
      const m = l.match(/\[([^\]]+)\]\(([^)]+)\)/);
      return m ? { label: m[1], url: m[2] } : null;
    }).filter(Boolean);
    body = body.replace(/^##\s+Sources\s*\n+[\s\S]*$/im, '').trimEnd();
  }

  // Also first paragraph fallback if no short answer yet
  if (!shortAnswer) {
    const paras = body.split(/\n\n+/);
    if (paras.length > 1 && !paras[0].startsWith('#')) {
      shortAnswer = paras[0].trim();
      body = paras.slice(1).join('\n\n').trimStart();
    }
  }

  return { title, shortAnswer, body, sources };
}

export default function AnswerView() {
  const { repoId } = useParams();
  const navigate = useNavigate();

  const [repoData, setRepoData] = useState(null);

  // Question & Chat State
  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [currentQuestionText, setCurrentQuestionText] = useState('');
  const [answerMarkdown, setAnswerMarkdown] = useState('');
  const [citations, setCitations] = useState([]);
  const [viewMode, setViewMode] = useState('preview'); // 'preview' | 'markdown'
  const [history, setHistory] = useState([]);
  const [activeHistoryIndex, setActiveHistoryIndex] = useState(-1);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [streamError, setStreamError] = useState(null);

  // Status steps state for thinking screen
  const [step1Done, setStep1Done] = useState(false);
  const [step1Detail, setStep1Detail] = useState('Searching repository files...');
  const [step2Done, setStep2Done] = useState(false);
  const [step3Done, setStep3Done] = useState(false);
  const [step3Detail, setStep3Detail] = useState('Verifying each statement against GitHub');

  // Sidebar
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Modal
  const [selectedCitation, setSelectedCitation] = useState(null);

  const abortStreamRef = useRef(null);
  const inputRef = useRef(null);
  const centerRef = useRef(null);

  // Load repo metadata
  useEffect(() => {
    if (!repoId) return;
    apiClient.getRepo(repoId)
      .then(setRepoData)
      .catch(() => setRepoData({ id: repoId, name: repoId, branch: 'main' }));
  }, [repoId]);

  const executeAsk = (queryText) => {
    const q = (queryText || question).trim();
    if (!q || isAsking) return;

    if (abortStreamRef.current) abortStreamRef.current();

    setQuestion('');
    setCurrentQuestionText(q);
    setIsAsking(true);
    setAnswerMarkdown('');
    setCitations([]);
    setStreamError(null);
    setStep1Done(false);
    setStep1Detail('Searching repository files...');
    setStep2Done(false);
    setStep3Done(false);
    setStep3Detail('Verifying each statement against GitHub');

    // Scroll center column to top
    if (centerRef.current) centerRef.current.scrollTop = 0;

    let acc = '';
    let accCitations = [];

    const cancel = apiClient.askStream(repoId, q, null, {
      onStatus: (s) => {
        if (!s) return;
        if (s.step === 1) {
          setStep1Done(s.state === 'done');
          setStep1Detail(s.detail || 'Searching repository files...');
        } else if (s.step === 2) {
          setStep2Done(s.state === 'done');
        } else if (s.step === 3) {
          setStep3Done(s.state === 'done');
          setStep3Detail(s.detail || 'Verifying each statement against GitHub');
        }
      },
      onToken: (token) => {
        acc += token;
        setAnswerMarkdown(acc);
      },
      onCitation: (c) => {
        accCitations.push(c);
        setCitations([...accCitations]);
      },
      onDone: () => {
        setIsAsking(false);
        abortStreamRef.current = null;
        const item = { question: q, answer: acc, citations: accCitations };
        setHistory((prev) => {
          const updated = [...prev, item];
          setActiveHistoryIndex(updated.length - 1);
          return updated;
        });
      },
      onError: (err) => {
        setIsAsking(false);
        abortStreamRef.current = null;
        setStreamError(String(err));
      },
    });

    abortStreamRef.current = cancel;
  };

  const handleStop = () => {
    if (abortStreamRef.current) {
      abortStreamRef.current();
      abortStreamRef.current = null;
    }
    setIsAsking(false);
  };

  const handleSelectHistory = (idx) => {
    const item = history[idx];
    if (!item) return;
    setActiveHistoryIndex(idx);
    setCurrentQuestionText(item.question);
    setAnswerMarkdown(item.answer);
    setCitations(item.citations || []);
    setStreamError(null);
  };

  const handleNewQuestion = () => {
    setAnswerMarkdown('');
    setCurrentQuestionText('');
    setActiveHistoryIndex(-1);
    setQuestion('');
    setStreamError(null);
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      executeAsk();
    }
  };

  const handleCopy = () => {
    if (answerMarkdown) {
      navigator.clipboard.writeText(answerMarkdown);
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    }
  };

  const handleDownload = () => {
    if (!answerMarkdown) return;
    const blob = new Blob([answerMarkdown], { type: 'text/markdown;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(repoData?.name || 'repo').replace('/', '_')}-answer.md`;
    a.click();
  };

  // Parse current answer
  const { title: displayTitle, shortAnswer, body: bodyContent, sources: mdSources } = parseAnswer(answerMarkdown);

  // TOC from H2 headings in body
  const tocHeadings = [];
  if (bodyContent) {
    [...bodyContent.matchAll(/^##\s+(.+)$/gm)].forEach((m) => {
      tocHeadings.push(m[1].trim());
    });
  }

  // Sources: prefer parsed markdown sources, then fall back to citations
  const uniqueSources = [];
  const seenPaths = new Set();

  if (mdSources.length > 0) {
    mdSources.forEach((s) => {
      if (!seenPaths.has(s.label)) {
        seenPaths.add(s.label);
        uniqueSources.push({ path: s.label, url: s.url, raw: s.label });
      }
    });
  } else {
    citations.forEach((c) => {
      const p = typeof c === 'string' ? c.split(':')[0] : c?.path;
      if (p && !seenPaths.has(p)) {
        seenPaths.add(p);
        uniqueSources.push({ path: p, raw: c });
      }
    });
  }

  const verifiedCount = uniqueSources.length || citations.length || 1;
  const repoDisplayName = repoData?.name || repoId;

  const suggestions = [
    'How does request routing work?',
    'Where is configuration initialized?',
    'What happens during application startup?',
  ];

  const defaultMockQuestions = [
    'Where is the database set up?',
    'How are errors handled?',
    'What happens on startup?',
  ];

  return (
    <div className="h-screen flex flex-col bg-[#0A0A0B] text-[#ECECEE] overflow-hidden font-['Inter',system-ui,sans-serif]">

      {/* ── Top Navbar ── */}
      <div className="h-[72px] flex-none flex items-center justify-between px-6 sm:px-8 border-b border-[#232328] bg-[#0D0D10] z-10">
        <div className="flex items-center gap-3.5">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="w-8 h-8 rounded-lg bg-[#16161B] border border-[#2B2B34] hover:border-[#4ADE80]/50 flex items-center justify-center transition-colors cursor-pointer"
            title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          >
            {sidebarOpen ? (
              <PanelLeftClose size={16} className="text-[#A1A1AA]" />
            ) : (
              <PanelLeftOpen size={16} className="text-[#A1A1AA]" />
            )}
          </button>
          <span className="font-extrabold text-[19px] sm:text-[20px] text-[#ECECEE] tracking-tight">
            RepoAsk
          </span>
          <span className="border border-[#2A2A30] rounded-full px-3.5 py-1 text-[12.5px] font-medium bg-[#131316] text-[#ECECEE]">
            {repoDisplayName} · {repoData?.branch || 'main'}
          </span>
          <span className="text-[12.5px] text-[#8B8B95] hidden md:block font-normal">
            Indexed from GitHub
          </span>
        </div>
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-medium text-[#ECECEE] bg-[#141418] hover:bg-[#1E1E24] hover:text-white border border-[#27272F] hover:border-[#383842] transition-all cursor-pointer shadow-xs active:scale-[0.98]"
        >
          <span>New repo</span>
        </button>
      </div>

      {/* ── 3-Column Workspace Grid ── */}
      <div className="flex-1 grid overflow-hidden transition-[grid-template-columns] duration-300 ease-in-out" style={{ gridTemplateColumns: sidebarOpen ? '240px minmax(0,1fr) 280px' : '0px minmax(0,1fr) 280px' }}>

        {/* ════ LEFT SIDEBAR (240px, collapsible) ════ */}
        <div className={`border-r border-[#1F1F24] bg-[#0D0D0F] flex flex-col gap-5 transition-all duration-300 ease-in-out ${sidebarOpen ? 'p-4 opacity-100 overflow-y-auto' : 'p-0 opacity-0 overflow-hidden pointer-events-none'}`}>
          <button
            onClick={handleNewQuestion}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-[13.5px] font-semibold text-[#052E16] bg-[#4ADE80] hover:bg-[#86EFAC] hover:text-[#02200D] border border-[#4ADE80] hover:border-[#86EFAC] shadow-sm transition-all duration-150 cursor-pointer active:scale-[0.99]"
          >
            <Plus size={16} strokeWidth={2.5} />
            <span>New question</span>
          </button>

          <div>
            <div className="cap pb-2 px-2.5 text-[11px] font-bold tracking-[0.08em] uppercase text-[#8B8B95]">
              Earlier questions
            </div>
            <div className="flex flex-col gap-1">
              {history.length > 0 ? (
                history.map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => handleSelectHistory(idx)}
                    title={item.question}
                    className={`row cursor-pointer truncate text-[13px] font-medium transition-all ${
                      activeHistoryIndex === idx
                        ? 'bg-[#14261C] border-l-2 border-[#4ADE80] text-[#4ADE80] font-semibold pl-2.5'
                        : 'text-[#B4B4BC] hover:text-[#ECECEE] hover:bg-[#131316]'
                    }`}
                  >
                    {item.question}
                  </div>
                ))
              ) : (
                defaultMockQuestions.map((q) => (
                  <div
                    key={q}
                    onClick={() => executeAsk(q)}
                    className="row text-[#B4B4BC] hover:text-[#ECECEE] hover:bg-[#131316] text-[13px] font-medium cursor-pointer truncate transition-colors"
                    title={`Click to ask: ${q}`}
                  >
                    {q}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* ════ CENTER COLUMN (Document & Pinned Sticky Input) ════ */}
        <div className="flex flex-col min-w-0 h-full overflow-hidden bg-[#0A0A0B]">

          {/* Scrollable Center Content */}
          <div ref={centerRef} className="flex-1 overflow-y-auto p-6 md:p-9 flex flex-col gap-5">

            {/* SCREEN 3: Thinking State */}
            {isAsking && !answerMarkdown && (
              <div className="flex flex-col gap-6 max-w-[880px]">
                <div className="flex flex-col gap-1.5">
                  <div className="text-[12px] font-bold tracking-wider uppercase text-[#8B8B95]">
                    Question
                  </div>
                  <div className="text-[20px] text-[#ECECEE] font-bold leading-snug">
                    {currentQuestionText}
                  </div>
                </div>

                {/* Status checklist card */}
                <div className="card flex flex-col gap-0.5 shadow-lg">
                  {/* Step 1 */}
                  <div className="flex gap-3.5 items-start py-3">
                    <CheckCircle />
                    <div>
                      <div className="text-[15px] font-semibold text-[#ECECEE]">Searched the repo</div>
                      <div className="text-[13.5px] text-[#8B8B95] mt-0.5">{step1Detail}</div>
                    </div>
                  </div>
                  {/* Step 2 */}
                  <div className="flex gap-3.5 items-start py-3">
                    <CheckCircle />
                    <div>
                      <div className="text-[15px] font-semibold text-[#ECECEE]">Followed connections between files</div>
                      <div className="text-[13.5px] text-[#8B8B95] mt-0.5">Checked who uses what</div>
                    </div>
                  </div>
                  {/* Step 3 */}
                  <div className="flex gap-3.5 items-start py-3">
                    {step3Done ? <CheckCircle /> : <SpinCircle />}
                    <div>
                      <div className="text-[15px] font-semibold text-[#ECECEE]">Checking the answer</div>
                      <div className="text-[13.5px] text-[#8B8B95] mt-0.5">{step3Detail}</div>
                    </div>
                  </div>
                </div>

                {/* Skeleton shimmer */}
                <div className="bg-[#0D0D0F] border border-[#232328] rounded-xl p-8 md:p-10 flex flex-col">
                  <div className="bar" style={{ width: '55%', height: '26px', marginBottom: '22px' }} />
                  <div className="bar" style={{ width: '100%' }} />
                  <div className="bar" style={{ width: '92%' }} />
                  <div className="bar" style={{ width: '70%', marginBottom: '28px' }} />
                  <div className="bar" style={{ width: '100%', height: '120px', borderRadius: '10px', marginBottom: '28px' }} />
                  <div className="bar" style={{ width: '100%' }} />
                  <div className="bar" style={{ width: '84%' }} />
                </div>

                <div>
                  <button onClick={handleStop} className="btn cursor-pointer">Stop</button>
                </div>
              </div>
            )}

            {/* Error State with Recovery Button */}
            {streamError && !isAsking && (
              <div className="p-5 border border-[#F87171]/40 bg-[#2A1315] rounded-xl flex items-center justify-between gap-4 max-w-[880px]">
                <div className="flex flex-col gap-1">
                  <div className="text-sm font-semibold text-[#FCA5A5]">Unable to complete request</div>
                  <div className="text-xs text-[#FCA5A5]/80">{streamError}</div>
                </div>
                <button
                  onClick={() => executeAsk(currentQuestionText)}
                  className="btn bg-[#F87171] text-[#2A1315] font-bold text-xs hover:bg-[#FCA5A5]"
                >
                  Retry Question
                </button>
              </div>
            )}

            {/* SCREEN 4: Answer or Empty State */}
            {(!isAsking || answerMarkdown) && (
              <>
                {/* Empty state — no question asked yet */}
                {!answerMarkdown && !isAsking && (
                  <div className="flex-1 flex flex-col items-center justify-center gap-5 py-24 text-center">
                    <div className="text-[34px] sm:text-[38px] font-extrabold text-[#ECECEE] tracking-tight">
                      What do you want to know?
                    </div>
                    <div className="text-[16px] text-[#8B8B95] max-w-[500px] leading-relaxed">
                      Ask anything about <span className="text-[#ECECEE] font-medium">{repoDisplayName}</span> — how it works, where things live, or how requests flow.
                    </div>
                    <div className="flex flex-wrap gap-2.5 justify-center mt-3">
                      {suggestions.map((s, i) => (
                        <button
                          key={i}
                          onClick={() => executeAsk(s)}
                          className="group flex items-center gap-2 px-4 py-2.5 rounded-xl text-[13.5px] font-medium text-[#ECECEE] bg-[#131316] hover:bg-[#1A1A22] border border-[#27272F] hover:border-[#3E3E48] transition-all cursor-pointer shadow-xs active:scale-[0.98]"
                        >
                          <span>{s}</span>
                          <ArrowUpRight size={14} className="text-[#71717A] group-hover:text-[#4ADE80] transition-colors" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Toolbar + Document — rendered when answer exists */}
                {answerMarkdown && (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      {/* Preview / Markdown toggle */}
                      <div className="flex gap-1 border border-[#26262C] rounded-[10px] p-[3px] bg-[#101013]">
                        <button
                          type="button"
                          onClick={() => setViewMode('preview')}
                          className={`min-h-[34px] px-3.5 border-0 rounded-[7px] text-[13px] font-semibold transition-all cursor-pointer ${
                            viewMode === 'preview'
                              ? 'bg-[#1C3322] text-[#4ADE80] shadow-xs'
                              : 'bg-transparent text-[#8B8B95] hover:text-[#ECECEE]'
                          }`}
                        >
                          Preview
                        </button>
                        <button
                          type="button"
                          onClick={() => setViewMode('markdown')}
                          className={`min-h-[34px] px-3.5 border-0 rounded-[7px] text-[13px] font-semibold transition-all cursor-pointer ${
                            viewMode === 'markdown'
                              ? 'bg-[#1C3322] text-[#4ADE80] shadow-xs'
                              : 'bg-transparent text-[#8B8B95] hover:text-[#ECECEE]'
                          }`}
                        >
                          Markdown
                        </button>
                      </div>

                      {/* Actions */}
                      <div className="flex flex-wrap gap-2.5 items-center">
                        <button
                          onClick={handleCopy}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12.5px] font-medium text-[#D4D4DA] hover:text-white bg-[#141418] hover:bg-[#1E1E24] border border-[#27272F] hover:border-[#383842] transition-all cursor-pointer shadow-xs active:scale-[0.98]"
                        >
                          {copyFeedback ? (
                            <>
                              <Check size={14} className="text-[#4ADE80]" />
                              <span className="text-[#4ADE80] font-semibold">Copied!</span>
                            </>
                          ) : (
                            <>
                              <Copy size={14} />
                              <span>Copy .md</span>
                            </>
                          )}
                        </button>
                        <button
                          onClick={handleDownload}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12.5px] font-medium text-[#D4D4DA] hover:text-white bg-[#141418] hover:bg-[#1E1E24] border border-[#27272F] hover:border-[#383842] transition-all cursor-pointer shadow-xs active:scale-[0.98]"
                        >
                          <Download size={14} />
                          <span>Download .md</span>
                        </button>
                      </div>
                    </div>

                    {/* Document card */}
                    <div id="top" className="bg-[#0D0D0F] border border-[#232328] rounded-xl p-8 sm:p-11 shadow-sm">
                      <div className="text-[13px] font-medium text-[#8B8B95] mb-2">
                        Question: <span className="text-[#ECECEE] font-medium">{currentQuestionText}</span>
                      </div>

                      <h1 className="m-0 mb-4 pb-3 border-b border-[#26262C] text-[30px] sm:text-[34px] font-bold tracking-tight text-[#ECECEE]">
                        {displayTitle}
                      </h1>

                      {/* Short answer callout */}
                      {shortAnswer && (
                        <div className="border border-[#1F5A38] bg-[#0E1A13] rounded-[10px] p-5 mb-6 shadow-xs">
                          <div className="text-[12px] font-bold tracking-wider uppercase text-[#4ADE80] mb-1.5">
                            Short answer
                          </div>
                          <div className="text-[16px] sm:text-[17px] font-medium leading-[1.65] text-[#ECECEE]">
                            {shortAnswer}
                          </div>
                        </div>
                      )}

                      {/* Body */}
                      {viewMode === 'preview' ? (
                        <MarkdownRenderer
                          content={bodyContent}
                          onCitationClick={(cit) => setSelectedCitation(cit)}
                        />
                      ) : (
                        <pre className="font-mono text-xs leading-relaxed text-[#ECECEE] bg-[#0A0A0B] p-4 rounded-lg border border-[#232328] overflow-x-auto whitespace-pre-wrap">
                          {answerMarkdown}
                        </pre>
                      )}
                    </div>

                    {/* Follow-up suggestions */}
                    <div className="flex flex-wrap gap-2 pt-2">
                      {suggestions.map((s, i) => (
                        <button
                          key={i}
                          onClick={() => executeAsk(s)}
                          className="group flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[12.5px] font-medium text-[#C4C4CC] hover:text-white bg-[#131316] hover:bg-[#1A1A22] border border-[#27272F] hover:border-[#383842] transition-all cursor-pointer shadow-xs active:scale-[0.98]"
                        >
                          <span>{s}</span>
                          <ArrowUpRight size={13} className="text-[#71717A] group-hover:text-[#4ADE80] transition-colors" />
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          {/* ── Pinned Sticky Input Footer ── */}
          <div className="flex-none px-6 md:px-9 py-3.5 border-t border-[#1F1F24] bg-[#0A0A0B]/95 backdrop-blur-md">
            <form
              onSubmit={(e) => { e.preventDefault(); executeAsk(); }}
              autoComplete="off"
              className="flex gap-2.5 items-stretch max-w-[1200px]"
            >
              <label htmlFor="q" className="sr-only">Ask a question</label>
              <input
                id="q"
                name="repo_query_input"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck="false"
                data-lpignore="true"
                ref={inputRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={answerMarkdown ? "Ask a follow-up about this repo" : "Ask anything about this repo (e.g. How does request routing work?)"}
                disabled={isAsking}
                className="flex-1 min-w-0 border border-[#2A2A30] rounded-[10px] px-4 text-[14.5px] bg-[#101013] text-[#ECECEE] placeholder-[#6B6B75] transition-colors focus:outline-none focus:border-[#4ADE80]"
                style={{ minHeight: '46px' }}
              />
              <button
                type="submit"
                disabled={isAsking || !question.trim()}
                className="shrink-0 border-0 bg-[#4ADE80] text-[#052E16] rounded-[10px] text-[14px] font-bold flex items-center gap-2 hover:bg-[#86EFAC] transition-colors disabled:opacity-50 cursor-pointer"
                style={{ minHeight: '46px', padding: '0 20px' }}
              >
                <span>Ask</span>
                <span className="kbd text-[11px] font-bold font-mono" style={{ color: '#052E16', background: '#86EFAC', borderColor: '#86EFAC' }}>
                  Ctrl ↵
                </span>
              </button>
            </form>
          </div>
        </div>

        {/* ════ RIGHT SIDEBAR (280px) ════ */}
        <div className="w-[280px] min-w-[280px] max-w-[280px] shrink-0 border-l border-[#1F1F24] bg-[#0D0D0F] flex flex-col gap-6 p-5 overflow-y-auto">

          {/* On this page (TOC with smooth scroll to headings) */}
          <div>
            <div className="cap mb-2.5 text-[11px] font-bold tracking-[0.08em] uppercase text-[#8B8B95]">
              On this page
            </div>
            <div className="flex flex-col gap-[3px] text-[13.5px]">
              {answerMarkdown ? (
                <>
                  <a
                    href="#top"
                    onClick={(e) => {
                      e.preventDefault();
                      if (centerRef.current) centerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className="row text-[#ECECEE] font-medium cursor-pointer"
                  >
                    {displayTitle}
                  </a>
                  {tocHeadings.map((h, i) => {
                    const slug = getSlug(h);
                    return (
                      <a
                        key={i}
                        href={`#${slug}`}
                        onClick={(e) => {
                          e.preventDefault();
                          const el = document.getElementById(slug);
                          if (el) {
                            el.scrollIntoView({ behavior: 'smooth' });
                          }
                        }}
                        className="row text-[#A1A1AA] hover:text-[#ECECEE] cursor-pointer truncate font-normal"
                        title={h}
                      >
                        {h}
                      </a>
                    );
                  })}
                </>
              ) : (
                <span className="text-[12.5px] text-[#8B8B95]">Sections will appear with answers.</span>
              )}
            </div>
          </div>

          {/* Sources on GitHub */}
          <div>
            <div className="cap mb-2.5 text-[11px] font-bold tracking-[0.08em] uppercase text-[#8B8B95]">
              Sources on GitHub
            </div>
            <div className="flex flex-col gap-1.5 text-[13.5px]">
              {uniqueSources.length > 0 ? (
                uniqueSources.map((src, i) => (
                  <div key={i} className="flex items-center justify-between group py-1 px-1.5 rounded-md hover:bg-[#131316] transition-colors">
                    <button
                      type="button"
                      onClick={() => setSelectedCitation(src.raw)}
                      className="flex items-center gap-1.5 text-left font-mono text-[12px] text-[#4ADE80] hover:text-[#86EFAC] bg-transparent border-0 p-0 cursor-pointer truncate max-w-[205px]"
                      title={`Preview ${src.path} code`}
                    >
                      <FileText size={13} className="flex-none opacity-70" />
                      <span className="truncate">{src.path}</span>
                    </button>
                    <a
                      href={`https://github.com/${repoDisplayName}/blob/${repoData?.branch || 'main'}/${src.path}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[#71717A] hover:text-[#4ADE80] text-xs px-1 font-mono transition-colors flex items-center"
                      title="Open on GitHub"
                    >
                      <ArrowUpRight size={13} />
                    </a>
                  </div>
                ))
              ) : (
                <span className="text-[12.5px] text-[#8B8B95]">Sources will appear with answers.</span>
              )}
            </div>
          </div>

          {/* Footer note */}
          <div className="mt-auto border-t border-[#1F1F24] pt-4 text-[12px] leading-[1.6] text-[#8B8B95]">
            Every statement in this answer was checked against the repository before it was shown.
          </div>
        </div>
      </div>

      {/* File viewer modal */}
      {selectedCitation && (
        <FileViewerModal
          repoId={repoId}
          citation={selectedCitation}
          onClose={() => setSelectedCitation(null)}
        />
      )}
    </div>
  );
}
