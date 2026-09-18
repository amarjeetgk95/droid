// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { DataTable, type Column } from './data-table';

afterEach(() => cleanup());

type Row = { id: string; name: string; pnl: number | null };

const rows: Row[] = [
  { id: 'r2', name: 'Beta', pnl: -20 },
  { id: 'r1', name: 'Alpha', pnl: 40 },
  { id: 'r3', name: 'Gamma', pnl: null },
];

function columns(extra: Partial<Column<Row>> = {}): Column<Row>[] {
  return [
    { key: 'name', header: 'Name', sortable: true },
    { key: 'pnl', header: 'P&L', align: 'right', sortable: true },
    { key: 'meta', header: 'Meta', render: (row) => <span>meta:{row.id}</span>, ...extra },
  ];
}

const keyExtractor = (row: Row) => row.id;

describe('DataTable', () => {
  it('renders headers, custom cells and rows', () => {
    render(<DataTable data={rows} columns={columns()} keyExtractor={keyExtractor} />);

    expect(screen.getByRole('columnheader', { name: /Name/ })).toBeTruthy();
    expect(screen.getByText('Alpha')).toBeTruthy();
    expect(screen.getByText('meta:r2')).toBeTruthy();
    expect(screen.getAllByRole('row')).toHaveLength(rows.length + 1);
  });

  it('renders the empty message when there is no data', () => {
    render(
      <DataTable
        data={[]}
        columns={columns()}
        keyExtractor={keyExtractor}
        emptyMessage="Nothing here"
      />,
    );

    expect(screen.getByText('Nothing here')).toBeTruthy();
  });

  it('sorts by a raw key and toggles order with aria-sort updates', () => {
    render(<DataTable data={rows} columns={columns()} keyExtractor={keyExtractor} />);

    const nameHeader = screen.getByRole('columnheader', { name: /Name/ });
    expect(nameHeader.getAttribute('aria-sort')).toBe('none');

    fireEvent.click(screen.getByRole('button', { name: /Name/ }));
    expect(nameHeader.getAttribute('aria-sort')).toBe('ascending');
    let cells = screen.getAllByRole('cell');
    expect(cells[0].textContent).toBe('Alpha');

    fireEvent.click(screen.getByRole('button', { name: /Name/ }));
    expect(nameHeader.getAttribute('aria-sort')).toBe('descending');
    cells = screen.getAllByRole('cell');
    expect(cells[0].textContent).toBe('Gamma');
  });

  it('uses sortValue for derived columns and keeps missing values last', () => {
    const derived: Column<Row>[] = [
      { key: 'name', header: 'Name' },
      {
        key: 'weighted',
        header: 'Weighted',
        sortable: true,
        sortValue: (row) => (row.pnl === null ? null : row.pnl * 2),
        render: (row) => <span>{row.pnl === null ? '—' : row.pnl * 2}</span>,
      },
    ];
    render(<DataTable data={rows} columns={derived} keyExtractor={keyExtractor} />);

    fireEvent.click(screen.getByRole('button', { name: /Weighted/ }));
    let cells = screen.getAllByRole('cell');
    expect(cells[1].textContent).toBe('-40');
    expect(cells[5].textContent).toBe('—');

    fireEvent.click(screen.getByRole('button', { name: /Weighted/ }));
    cells = screen.getAllByRole('cell');
    expect(cells[0].textContent).toBe('Alpha');
    expect(cells[1].textContent).toBe('80');
    expect(cells[5].textContent).toBe('—');
  });

  it('paginates and disables Prev on the first page', () => {
    const many: Row[] = Array.from({ length: 12 }, (_, i) => ({
      id: `r${i + 1}`,
      name: `Row ${i + 1}`,
      pnl: i,
    }));
    render(<DataTable data={many} columns={columns()} keyExtractor={keyExtractor} pageSize={10} />);

    expect(screen.getByText('Showing 1 to 10 of 12')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Prev' })).toHaveProperty('disabled', true);
    expect(screen.queryByText('Row 11')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Showing 11 to 12 of 12')).toBeTruthy();
    expect(screen.getByText('Row 11')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', true);
  });

  it('renders every row when pagination is disabled', () => {
    const many: Row[] = Array.from({ length: 12 }, (_, i) => ({
      id: `r${i + 1}`,
      name: `Row ${i + 1}`,
      pnl: i,
    }));
    render(
      <DataTable
        data={many}
        columns={columns()}
        keyExtractor={keyExtractor}
        pageSize={10}
        paginate={false}
      />,
    );

    expect(screen.getAllByRole('row')).toHaveLength(13);
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
  });

  it('invokes onRowClick with the row', () => {
    const onRowClick = vi.fn();
    render(
      <DataTable
        data={rows}
        columns={columns()}
        keyExtractor={keyExtractor}
        onRowClick={onRowClick}
      />,
    );

    fireEvent.click(screen.getByText('Alpha'));
    expect(onRowClick).toHaveBeenCalledWith(rows[1]);
  });
});
