export function clamp(value: number, lo: number, hi: number): number {
  if (value < lo) return hi;
  if (value > hi) return lo;
  return value;
}
