export function percent(value: number | null): string {
  return value === null ? 'Not reported' : `${new Intl.NumberFormat('en', { maximumFractionDigits: 1 }).format(value)}%`;
}

export function dateTime(value: string | null): string {
  return value === null ? 'Not reported' : new Intl.DateTimeFormat('en', {
    dateStyle: 'medium', timeStyle: 'long',
  }).format(new Date(value));
}

export function duration(minutes: number | null, fallback: string): string {
  if (minutes === null || minutes <= 0) return fallback;
  for (const [unit, size] of [['week', 10080], ['day', 1440], ['hour', 60], ['minute', 1]] as const) {
    if (minutes % size === 0) {
      const count = minutes / size;
      return `${count} ${unit}${count === 1 ? '' : 's'}`;
    }
  }
  return fallback;
}

export function untilReset(value: string | null, now: number): string {
  if (value === null) return 'Reset time not reported';
  const minutes = Math.ceil((Date.parse(value) - now) / 60_000);
  if (minutes <= 0) return 'Reset time passed — refresh usage for the current limit';
  if (minutes < 60) return `Resets in ${minutes}m`;
  if (minutes < 1440) return `Resets in ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `Resets in ${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`;
}
