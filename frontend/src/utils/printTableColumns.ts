/** Estimate compact printed widths in mm; long text wraps instead of widening the page. */
export function compactPrintWidth(
  heading: string,
  values: Array<string | number | null | undefined>,
  maximum: number,
  fontSize = 10.5,
  padding = 3,
): number {
  const textWidth = (text: string, size: number) =>
    Math.max(0, ...text.split('\n').map((line) => Array.from(line.trim()).length)) * size * 0.56 * 25.4 / 96
  const content = Math.max(textWidth(heading, 9), ...values.map((value) => textWidth(String(value ?? '—'), fontSize)))
  return Math.round(Math.min(maximum, Math.max(8, content + padding)) * 10) / 10
}

/** Give the remaining page width to the name and other existing prose columns. */
export function printColgroup(pageWidth: number, columns: Array<{ width: number } | { grow: number }>): string {
  const fixed = columns.reduce((total, column) => total + ('width' in column ? column.width : 0), 0)
  const growth = columns.reduce((total, column) => total + ('grow' in column ? column.grow : 0), 0)
  return `<colgroup>${columns.map((column) => {
    const width = 'width' in column ? column.width : (pageWidth - fixed) * column.grow / growth
    return `<col style="width:${width.toFixed(1)}mm" />`
  }).join('')}</colgroup>`
}
