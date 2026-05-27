import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import ProcessTimeline from './ProcessTimeline';
import type { ProcessEvent } from '../types/chat';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

afterEach(() => cleanup());

const events: ProcessEvent[] = [
  {
    id: 'skills',
    type: 'skill_manifest',
    role: 'operator',
    skills: [{ name: 'file_manager', description: 'Files', category: 'file_manager' }],
  },
  {
    id: 'skill-use',
    type: 'skill_use',
    name: 'file_manager',
    phase: 'answering',
    reason: 'Need file context',
  },
  {
    id: 'tool',
    type: 'tool_call',
    name: 'file_read',
    args: { path: 'a.txt' },
  },
];

describe('ProcessTimeline', () => {
  test('renders a compact summary', () => {
    render(<ProcessTimeline events={events} />);

    expect(screen.getByText('Process')).toBeTruthy();
    expect(screen.getByText('1 Skills')).toBeTruthy();
    expect(screen.getByText('1 Skill use')).toBeTruthy();
    expect(screen.getByText('1 Tool')).toBeTruthy();
  });

  test('shows details when expanded', () => {
    render(<ProcessTimeline events={events} />);

    fireEvent.click(screen.getByText('Process'));

    expect(screen.getByText('Loaded Skills')).toBeTruthy();
    expect(screen.getByText('file_manager')).toBeTruthy();
    expect(screen.getByText('Using Skill')).toBeTruthy();
    expect(screen.getByText('file_read')).toBeTruthy();
  });
});
