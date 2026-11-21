import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import HomeView from '@/views/HomeView';
import AnswerView from '@/views/AnswerView';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#0A0A0B] text-[#ECECEE] font-['Inter',system-ui,sans-serif] antialiased flex flex-col selection:bg-[#12261A] selection:text-[#4ADE80]">
        <Routes>
          {/* Home Route (Screen 1: Paste link & Screen 2: Reading repo) */}
          <Route path="/" element={<HomeView />} />

          {/* Repo Workspace (Screen 3: Thinking & Screen 4: Answer Document) */}
          <Route path="/repo/:repoId" element={<AnswerView />} />
          <Route path="/repo/:repoId/ask" element={<Navigate to=".." relative="path" replace />} />
          <Route path="/repo/:repoId/*" element={<Navigate to=".." relative="path" replace />} />

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
