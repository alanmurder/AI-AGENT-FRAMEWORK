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
    expect(screen.getByText('1 Skill')).toBeTruthy();
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

  test('counts duplicate loaded skills once', () => {
    render(
      <ProcessTimeline
        events={[
          events[0],
          {
            id: 'skills-again',
            type: 'skill_manifest',
            role: 'operator',
            skills: [{ name: 'file_manager', description: 'Files', category: 'file_manager' }],
          },
        ]}
      />,
    );

    expect(screen.getByText('1 Skill')).toBeTruthy();
    expect(screen.queryByText('2 Skills')).toBeNull();
  });

  test('renders a meaningful progress-only summary', () => {
    render(
      <ProcessTimeline
        events={[
          {
            id: 'progress',
            type: 'progress',
            stage: 'searching',
            content: 'Searching files',
          },
        ]}
      />,
    );

    expect(screen.getByText('Process')).toBeTruthy();
    expect(screen.getByText('1 Progress')).toBeTruthy();
    expect(screen.queryByText('0 Skills')).toBeNull();
    expect(screen.queryByText('0 Skill use')).toBeNull();
    expect(screen.queryByText('0 Tool')).toBeNull();
  });

  test('contains long skill names and tool args inside the timeline', () => {
    const longValue = 'very-long-unbroken-value-that-should-wrap-inside-the-chat-bubble'.repeat(3);
    const { container } = render(
      <ProcessTimeline
        events={[
          {
            id: 'long-skill',
            type: 'skill_manifest',
            skills: [{ name: longValue, description: 'Long', category: 'long' }],
          },
          {
            id: 'long-tool',
            type: 'tool_call',
            name: longValue,
            args: { value: longValue },
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByText('Process'));

    const skillTag = screen.getAllByText(longValue)[0].closest('.ant-tag') as HTMLElement;
    expect(skillTag.style.overflowWrap).toBe('anywhere');
    expect(skillTag.style.wordBreak).toBe('break-word');

    const args = container.querySelector('pre') as HTMLPreElement;
    expect(args.style.maxWidth).toBe('100%');
    expect(args.style.overflowX).toBe('auto');
    expect(args.style.overflowWrap).toBe('anywhere');
    expect(args.style.wordBreak).toBe('break-word');
  });
});
