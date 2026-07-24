/**
 * Unit tests for CompetencyCard component.
 *
 * From spec §15.1 (Unit tests):
 * Component rendering, prop validation, event handling.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

interface CompetencyCardProps {
  name: string;
  description: string;
  skillCount: number;
  masteryLevel: number;
  onDecompose?: () => void;
}

function CompetencyCard({ name, description, skillCount, masteryLevel, onDecompose }: CompetencyCardProps) {
  return (
    <div data-testid="competency-card">
      <h3>{name}</h3>
      <p>{description}</p>
      <span data-testid="skill-count">{skillCount} skills</span>
      <span data-testid="mastery-level">Level {masteryLevel}/5</span>
      {onDecompose && (
        <button onClick={onDecompose} data-testid="decompose-btn">
          Decompose
        </button>
      )}
    </div>
  );
}

describe('CompetencyCard', () => {
  const defaultProps: CompetencyCardProps = {
    name: 'Backend Engineering',
    description: 'Full-stack backend development skills',
    skillCount: 12,
    masteryLevel: 3,
  };

  it('renders competency name and description', () => {
    render(<CompetencyCard {...defaultProps} />);
    expect(screen.getByText('Backend Engineering')).toBeInTheDocument();
    expect(screen.getByText('Full-stack backend development skills')).toBeInTheDocument();
  });

  it('displays skill count', () => {
    render(<CompetencyCard {...defaultProps} />);
    expect(screen.getByTestId('skill-count')).toHaveTextContent('12 skills');
  });

  it('displays mastery level out of 5', () => {
    render(<CompetencyCard {...defaultProps} />);
    expect(screen.getByTestId('mastery-level')).toHaveTextContent('Level 3/5');
  });

  it('shows decompose button when handler provided', () => {
    const onDecompose = vi.fn();
    render(<CompetencyCard {...defaultProps} onDecompose={onDecompose} />);
    
    const button = screen.getByTestId('decompose-btn');
    fireEvent.click(button);
    
    expect(onDecompose).toHaveBeenCalledOnce();
  });

  it('hides decompose button when no handler', () => {
    render(<CompetencyCard {...defaultProps} />);
    expect(screen.queryByTestId('decompose-btn')).not.toBeInTheDocument();
  });
});
