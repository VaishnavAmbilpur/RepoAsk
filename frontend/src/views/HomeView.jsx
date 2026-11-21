import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen,
  GitBranch,
  ShieldCheck,
  ArrowRight,
  FolderGit2,
  X,
  CheckCircle2,
  Github
} from 'lucide-react';
import { apiClient } from '@/api/client';

const SAMPLE_REPOS = [
  { name: 'pallets/flask', url: 'https://github.com/pallets/flask' },
  { name: 'expressjs/express', url: 'https://github.com/expressjs/express' },
  { name: 'fastapi/fastapi', url: 'https://github.com/fastapi/fastapi' },
];

export default function HomeView() {
  const [url, setUrl] = useState('');
  const [isReading, setIsReading] = useState(false);
  const [readingRepoName, setReadingRepoName] = useState('');
  const [readingStep, setReadingStep] = useState(1);
  const [progressPercent, setProgressPercent] = useState(25);
  const [estimatedSeconds, setEstimatedSeconds] = useState(35);
  const [filesFound, setFilesFound] = useState(180);
  const [errorMessage, setErrorMessage] = useState('');
  const [recentRepos, setRecentRepos] = useState([]);
  const [showSupportedModal, setShowSupportedModal] = useState(false);

  const navigate = useNavigate();
  const abortControllerRef = useRef(null);

  // Load recently indexed repositories
  useEffect(() => {
    apiClient.listRepos()
      .then((data) => {
        if (data?.repositories) {
          setRecentRepos(data.repositories);
        }
      })
      .catch(() => {});
  }, []);

  // Timer countdown while reading
  useEffect(() => {
    let timer;
    if (isReading && estimatedSeconds > 3) {
      timer = setInterval(() => {
        setEstimatedSeconds((s) => Math.max(2, s - 1));
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isReading, estimatedSeconds]);

  const handleStartAnalysis = async (targetUrl) => {
    const rawUrl = (targetUrl || url).trim();
    if (!rawUrl) return;

    setErrorMessage('');

    // Extract name for display
    const match = rawUrl.match(/(?:https?:\/\/)?(?:www\.)?github\.com\/([^/\s?#]+)\/([^/\s?#]+)/i);
    const repoName = match ? `${match[1]}/${match[2].replace(/\.git$/, '')}` : rawUrl;

    setReadingRepoName(repoName);
    setIsReading(true);
    setReadingStep(1);
    setProgressPercent(20);
    setEstimatedSeconds(35);

    const s2 = setTimeout(() => {
      setReadingStep(2);
      setProgressPercent(45);
    }, 1200);

    const s3 = setTimeout(() => {
      setReadingStep(3);
      setProgressPercent(68);
    }, 3200);

    const s4 = setTimeout(() => {
      setReadingStep(4);
      setProgressPercent(88);
    }, 6000);

    try {
      const res = await apiClient.indexRepo(rawUrl);
      const data = res.data;
      const repoId = data.repo_id;
      if (data.files_indexed) {
        setFilesFound(data.files_indexed);
      }

      clearTimeout(s2);
      clearTimeout(s3);
      clearTimeout(s4);

      setReadingStep(5);
      setProgressPercent(100);

      setTimeout(() => {
        navigate(`/repo/${repoId}`);
      }, 400);
    } catch (err) {
      clearTimeout(s2);
      clearTimeout(s3);
      clearTimeout(s4);
      setIsReading(false);
      setErrorMessage(err.message || 'Failed to index repository. Please verify the URL.');
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsReading(false);
    setErrorMessage('');
  };

  // ----------------------------------------------------
  // SCREEN 2: Reading the repo
  // ----------------------------------------------------
  if (isReading) {
    return (
      <div className="h-screen overflow-hidden flex flex-col bg-[#0A0A0B] text-[#ECECEE] font-['Inter',system-ui,sans-serif]">
        {/* Top Navbar */}
        <div className="h-[72px] flex-none box-border flex items-center justify-between px-6 sm:px-8 border-b border-[#232328] bg-[#0D0D10]">
          <div className="flex items-center gap-3.5">
            <span className="font-extrabold text-[19px] sm:text-[20px] text-[#ECECEE] tracking-tight">
              RepoAsk
            </span>
            <span className="border border-[#2A2A30] rounded-full px-3.5 py-1 text-xs font-medium text-[#ECECEE] bg-[#131316]">
              {readingRepoName} · main
            </span>
          </div>
          <button
            onClick={handleCancel}
            className="px-4 py-2 rounded-lg text-xs font-medium text-[#D4D4DA] hover:text-white bg-[#141418] hover:bg-[#1E1E24] border border-[#27272F] transition-all cursor-pointer"
          >
            Cancel
          </button>
        </div>

        {/* Center Card */}
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="w-full max-w-[580px] p-7 md:p-8 flex flex-col gap-5 shadow-2xl bg-[#0D0D10] border border-[#232328] rounded-2xl">
            <div>
              <div className="text-[11px] font-bold tracking-wider uppercase text-[#8B8B95] mb-1.5">Step 2 of 3</div>
              <h1 className="m-0 text-2xl font-bold text-[#ECECEE]">
                Reading {readingRepoName}
              </h1>
              <p className="mt-1.5 mb-0 text-[13.5px] text-[#A1A1AA]">
                About {estimatedSeconds} seconds remaining.
              </p>
            </div>

            {/* Progress Bar */}
            <div className="h-1.5 rounded-full bg-[#1F1F24] overflow-hidden">
              <div
                className="h-1.5 rounded-full bg-[#4ADE80] transition-all duration-500 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>

            {/* Steps Checklist */}
            <div className="flex flex-col divide-y divide-[#1B1B20]">
              {/* Step 1 */}
              <div className="flex gap-3 items-center py-2.5">
                <CheckCircle2 size={18} className="text-[#4ADE80] flex-none" />
                <div>
                  <div className="text-[14px] font-semibold text-[#ECECEE]">
                    Downloaded repository
                  </div>
                  <div className="text-[12px] text-[#8B8B95]">
                    {filesFound} files found
                  </div>
                </div>
              </div>

              {/* Step 2 */}
              <div className="flex gap-3 items-center py-2.5">
                {readingStep >= 2 ? (
                  <CheckCircle2 size={18} className="text-[#4ADE80] flex-none" />
                ) : (
                  <div className="w-[18px] h-[18px] rounded-full border border-[#2E2E36] flex-none" />
                )}
                <div>
                  <div className={`text-[14px] font-semibold ${readingStep >= 2 ? 'text-[#ECECEE]' : 'text-[#6B6B75]'}`}>
                    Filtered non-code files
                  </div>
                  <div className="text-[12px] text-[#8B8B95]">
                    Skipped build files and locks
                  </div>
                </div>
              </div>

              {/* Step 3 */}
              <div className="flex gap-3 items-center py-2.5">
                {readingStep > 3 ? (
                  <CheckCircle2 size={18} className="text-[#4ADE80] flex-none" />
                ) : readingStep === 3 ? (
                  <div className="w-[18px] h-[18px] rounded-full border-2 border-[#26262C] border-t-[#4ADE80] animate-spin flex-none" />
                ) : (
                  <div className="w-[18px] h-[18px] rounded-full border border-[#2E2E36] flex-none" />
                )}
                <div>
                  <div className={`text-[14px] font-semibold ${readingStep >= 3 ? 'text-[#ECECEE]' : 'text-[#6B6B75]'}`}>
                    Chunked code by language
                  </div>
                  <div className="text-[12px] text-[#8B8B95]">
                    {readingStep >= 3 ? 'Language-aware AST splitting' : 'Pending'}
                  </div>
                </div>
              </div>

              {/* Step 4 */}
              <div className="flex gap-3 items-center py-2.5">
                {readingStep > 4 ? (
                  <CheckCircle2 size={18} className="text-[#4ADE80] flex-none" />
                ) : readingStep === 4 ? (
                  <div className="w-[18px] h-[18px] rounded-full border-2 border-[#26262C] border-t-[#4ADE80] animate-spin flex-none" />
                ) : (
                  <div className="w-[18px] h-[18px] rounded-full border border-[#2E2E36] flex-none" />
                )}
                <div>
                  <div className={`text-[14px] font-semibold ${readingStep >= 4 ? 'text-[#ECECEE]' : 'text-[#6B6B75]'}`}>
                    Generated embeddings
                  </div>
                  <div className="text-[12px] text-[#8B8B95]">
                    {readingStep >= 4 ? 'FastEmbed in-process indexing' : 'Pending'}
                  </div>
                </div>
              </div>

              {/* Step 5 */}
              <div className="flex gap-3 items-center py-2.5">
                {readingStep === 5 ? (
                  <CheckCircle2 size={18} className="text-[#4ADE80] flex-none" />
                ) : (
                  <div className="w-[18px] h-[18px] rounded-full border border-[#2E2E36] flex-none" />
                )}
                <div>
                  <div className={`text-[14px] font-semibold ${readingStep === 5 ? 'text-[#ECECEE]' : 'text-[#6B6B75]'}`}>
                    Ready to answer
                  </div>
                  <div className="text-[12px] text-[#8B8B95]">
                    {readingStep === 5 ? 'Ready' : 'Pending'}
                  </div>
                </div>
              </div>
            </div>

            <div className="border-t border-[#1F1F24] pt-3 text-[12px] text-[#8B8B95]">
              Read-only index. No repository changes.
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------
  // SCREEN 1: Home (Fit without page scroll)
  // ----------------------------------------------------
  return (
    <div className="h-screen overflow-hidden flex flex-col justify-between bg-[#0A0A0B] text-[#ECECEE] font-['Inter',system-ui,sans-serif]">
      {/* Top Navbar */}
      <div className="h-[72px] flex-none box-border flex items-center justify-between px-6 sm:px-8 border-b border-[#232328] bg-[#0D0D10]">
        <div className="flex items-center gap-2.5">
          <span className="font-extrabold text-[19px] sm:text-[20px] text-[#ECECEE] tracking-tight">
            RepoAsk
          </span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <button
            type="button"
            onClick={() => {
              const el = document.getElementById('features-strip');
              el?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="px-4 py-2 rounded-lg text-[13px] font-medium text-[#A1A1AA] hover:text-[#4ADE80] hover:bg-[#141418] transition-all cursor-pointer"
          >
            How it works
          </button>
          <button
            type="button"
            onClick={() => setShowSupportedModal(true)}
            className="px-4 py-2 rounded-lg text-[13px] font-medium text-[#A1A1AA] hover:text-[#4ADE80] hover:bg-[#141418] transition-all cursor-pointer"
          >
            Supported repos
          </button>
        </div>
      </div>

      {/* Main Center Content (Balanced Vertical Rhythm, No Scroll) */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 max-w-[880px] mx-auto w-full gap-5">
        
        {/* Hero Title & Subtitle */}
        <div className="text-center flex flex-col gap-2">
          <h1 className="m-0 text-[34px] sm:text-[44px] md:text-[48px] leading-[1.12] font-extrabold tracking-[-0.025em] text-[#ECECEE]">
            Ask any GitHub repo <span className="text-[#4ADE80]">anything.</span>
          </h1>
          <p className="m-0 text-[15px] sm:text-[16px] leading-relaxed text-[#A1A1AA] max-w-[540px] mx-auto">
            Paste a link. Get clear answers as short documents with diagrams. No code to read.
          </p>
        </div>

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleStartAnalysis();
          }}
          autoComplete="off"
          className="flex flex-col sm:flex-row gap-2.5 w-full max-w-[720px]"
        >
          <label htmlFor="repo" className="sr-only">
            GitHub repository link
          </label>
          <div className="flex-1 flex items-center bg-[#101013] border border-[#27272F] focus-within:border-[#4ADE80] focus-within:ring-2 focus-within:ring-[#4ADE80]/20 rounded-xl px-4 min-h-[50px] transition-all shadow-sm">
            <Github size={18} className="text-[#71717A] flex-none mr-3" />
            <input
              id="repo"
              name="repo_url_input"
              type="url"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck="false"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              className="w-full bg-transparent text-[15px] text-[#ECECEE] placeholder-[#5A5A66] outline-none"
            />
          </div>
          <button
            type="submit"
            className="min-h-[50px] px-6 border border-[#4ADE80] bg-[#4ADE80] text-[#052E16] rounded-xl text-[14.5px] font-bold hover:bg-[#86EFAC] hover:border-[#86EFAC] transition-all cursor-pointer flex items-center justify-center gap-2 active:scale-[0.98] shadow-sm flex-none"
          >
            <span>Analyze repo</span>
            <ArrowRight size={16} />
          </button>
        </form>

        {errorMessage && (
          <div className="text-xs text-[#F87171] bg-[#2A1315] border border-[#F87171]/40 rounded-lg px-4 py-2.5 max-w-[720px] w-full text-center">
            {errorMessage}
          </div>
        )}

        {/* Quick Launch Pills (Recent or Samples) */}
        <div className="flex flex-wrap gap-2 items-center justify-center text-[12.5px] text-[#8B8B95]">
          <span className="font-medium text-[#71717A]">
            {recentRepos.length > 0 ? 'Recent / Samples:' : 'Try one:'}
          </span>
          {recentRepos.length > 0
            ? recentRepos.slice(0, 3).map((repo) => (
                <button
                  key={repo.id}
                  type="button"
                  onClick={() => navigate(`/repo/${repo.id}`)}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[12px] font-medium text-[#D4D4DA] hover:text-[#4ADE80] bg-[#121216] hover:bg-[#142318] border border-[#232328] hover:border-[#27673D] transition-all cursor-pointer group"
                >
                  <FolderGit2 size={13} className="text-[#71717A] group-hover:text-[#4ADE80] transition-colors" />
                  <span>{repo.name}</span>
                </button>
              ))
            : SAMPLE_REPOS.map((sample) => (
                <button
                  key={sample.name}
                  type="button"
                  onClick={() => {
                    setUrl(sample.url);
                    handleStartAnalysis(sample.url);
                  }}
                  className="px-2.5 py-1 rounded-md text-[12px] font-medium text-[#C4C4CC] hover:text-white bg-[#121216] hover:bg-[#1A1A22] border border-[#232328] hover:border-[#383842] transition-all cursor-pointer active:scale-[0.98]"
                >
                  {sample.name}
                </button>
              ))}
        </div>

        {/* 3 Value Proposition Cards (Compact) */}
        <div
          id="features-strip"
          className="grid grid-cols-1 md:grid-cols-3 gap-3 w-full max-w-[880px] text-left mt-1"
        >
          <div className="p-4 rounded-xl bg-[#0D0D10] border border-[#202026] hover:border-[#27673D] hover:bg-[#0F1411] transition-all duration-200 shadow-xs flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[#12261A] border border-[#1F5A38] flex items-center justify-center text-[#4ADE80]">
                <BookOpen size={13} />
              </div>
              <div className="text-[14px] font-semibold text-[#ECECEE]">
                Plain-language answers
              </div>
            </div>
            <div className="text-[12.5px] leading-relaxed text-[#8B8B95]">
              Short documents with verified citations. No code to read.
            </div>
          </div>

          <div className="p-4 rounded-xl bg-[#0D0D10] border border-[#202026] hover:border-[#27673D] hover:bg-[#0F1411] transition-all duration-200 shadow-xs flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[#12261A] border border-[#1F5A38] flex items-center justify-center text-[#4ADE80]">
                <GitBranch size={13} />
              </div>
              <div className="text-[14px] font-semibold text-[#ECECEE]">
                Diagrams when they help
              </div>
            </div>
            <div className="text-[12.5px] leading-relaxed text-[#8B8B95]">
              Flowcharts for processes, tables for structured data.
            </div>
          </div>

          <div className="p-4 rounded-xl bg-[#0D0D10] border border-[#202026] hover:border-[#27673D] hover:bg-[#0F1411] transition-all duration-200 shadow-xs flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[#12261A] border border-[#1F5A38] flex items-center justify-center text-[#4ADE80]">
                <ShieldCheck size={13} />
              </div>
              <div className="text-[14px] font-semibold text-[#ECECEE]">
                Checked against the repo
              </div>
            </div>
            <div className="text-[12.5px] leading-relaxed text-[#8B8B95]">
              Every statement checked against actual files and line numbers.
            </div>
          </div>
        </div>
      </div>

      {/* Clean Footer */}
      <div className="flex-none pb-4 text-center text-[11.5px] text-[#6B6B75]">
        Public GitHub repositories only. Python, JavaScript, TypeScript, Go, Rust, Java, C/C++.
      </div>

      {/* Supported Repos Modal */}
      {showSupportedModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="bg-[#0F0F12] border border-[#26262C] rounded-2xl max-w-[480px] w-full p-5 shadow-2xl flex flex-col gap-3.5">
            <div className="flex items-center justify-between pb-2.5 border-b border-[#202026]">
              <div className="text-[16px] font-bold text-[#ECECEE]">Supported Repositories</div>
              <button
                type="button"
                onClick={() => setShowSupportedModal(false)}
                className="text-[#8B8B95] hover:text-[#ECECEE] p-1 rounded-md transition-colors cursor-pointer"
              >
                <X size={17} />
              </button>
            </div>
            <div className="flex flex-col gap-2.5 text-[13.5px] text-[#D4D4DA] leading-relaxed">
              <p className="m-0 text-[#8B8B95] text-[13px]">
                RepoAsk indexes public GitHub repositories and splits code into language-aware chunks.
              </p>
              <div className="grid grid-cols-2 gap-2 mt-1">
                <div className="p-2.5 rounded-lg bg-[#141418] border border-[#202026]">
                  <div className="text-[11px] font-semibold text-[#4ADE80] uppercase">Languages</div>
                  <div className="text-[12px] text-[#ECECEE] mt-1 font-mono">Python, JS, TS, Go, Rust, C/C++, Java</div>
                </div>
                <div className="p-2.5 rounded-lg bg-[#141418] border border-[#202026]">
                  <div className="text-[11px] font-semibold text-[#4ADE80] uppercase">Formats</div>
                  <div className="text-[12px] text-[#ECECEE] mt-1 font-mono">Markdown, JSON, YAML, TOML, SQL, HTML</div>
                </div>
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowSupportedModal(false)}
                className="px-4 py-1.5 rounded-lg text-[13px] font-semibold text-[#052E16] bg-[#4ADE80] hover:bg-[#86EFAC] transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
