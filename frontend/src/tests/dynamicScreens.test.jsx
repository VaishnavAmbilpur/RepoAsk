import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MarkdownRenderer from '@/components/MarkdownRenderer';

describe('RepoAsk Screen & Component Requirements', () => {
  it('renders markdown with headings and formatted badges', () => {
    const markdown = `# Arena Allocator\n\n> **Short answer:** High performance allocator.\n\n## How it works\n\nUses \`malloc\` and \`free\` efficiently.`;
    render(<MarkdownRenderer content={markdown} />);
    
    expect(screen.getByText('Arena Allocator')).toBeInTheDocument();
    expect(screen.getByText('High performance allocator.')).toBeInTheDocument();
    expect(screen.getByText('How it works')).toBeInTheDocument();
    expect(screen.getByText('malloc')).toBeInTheDocument();
  });

  it('renders inline code without breaking paragraph structure', () => {
    const textWithCode = `The function calls \`alloc()\` to get memory.`;
    const { container } = render(<MarkdownRenderer content={textWithCode} />);
    const codeEl = container.querySelector('code');
    expect(codeEl).not.toBeNull();
    expect(codeEl.textContent).toBe('alloc()');
  });
});
