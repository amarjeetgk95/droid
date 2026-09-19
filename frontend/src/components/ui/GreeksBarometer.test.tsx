// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { GreeksBarometer } from './GreeksBarometer';

afterEach(() => cleanup());

describe('GreeksBarometer component', () => {
  it('renders greeks with formatted values', () => {
    render(
      <GreeksBarometer
        delta={0.52}
        theta={-15.4}
        gamma={0.0018}
        vega={8.5}
        iv={14.2}
        lotSize={25}
      />,
    );

    expect(screen.getByText('+0.520')).toBeDefined();
    expect(screen.getByText('-15.40 pts')).toBeDefined();
    expect(screen.getByText('0.0018')).toBeDefined();
    expect(screen.getByText('8.50 pts')).toBeDefined();
    expect(screen.getByText('14.2%')).toBeDefined();
  });

  it('renders placeholders gracefully when values are absent', () => {
    render(<GreeksBarometer />);
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });
});
