/**
 * Maps a normalized UTCI score (0-1) to an aesthetic hex color code.
 * - < 0.3: Comfortable (Green)
 * - < 0.6: Moderate heat stress (Amber)
 * - < 0.8: High heat stress (Red)
 * - >= 0.8: Extreme heat stress (Purple)
 */
export const utciColor = (score: number): string => {
  if (score < 0.3) return '#22c55e'; // Green — Comfortable
  if (score < 0.6) return '#f59e0b'; // Amber — Moderate
  if (score < 0.8) return '#ef4444'; // Red — Hot
  return '#7c3aed';                  // Purple — Extreme
};

export const getComfortLabel = (score: number): string => {
  if (score < 0.3) return 'Comfortable';
  if (score < 0.6) return 'Moderate Stress';
  if (score < 0.8) return 'High Stress';
  return 'Extreme Stress';
};
