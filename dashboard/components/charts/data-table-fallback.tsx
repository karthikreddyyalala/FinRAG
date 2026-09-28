export function DataTableFallback({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: string[];
  rows: (string | number)[][];
}) {
  return (
    <details className="mt-4">
      <summary className="cursor-pointer text-sm text-[var(--color-muted)] hover:text-[var(--color-text)]">
        View as table
      </summary>
      <table className="mt-3 w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            {columns.map((col) => (
              <th key={col} scope="col" className="px-2 py-2 text-left font-medium text-[var(--color-muted)]">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-[var(--color-border)]">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={`px-2 py-2 text-[var(--color-text)] ${j > 0 ? "font-[family-name:var(--font-mono)] tabular-nums" : ""}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
