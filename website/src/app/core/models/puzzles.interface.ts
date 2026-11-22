// The JSON written by build-scripts/process-puzzles.js from ../advent_of_code and
// ../project_euler. Generated at build time, so it always matches this build.

export interface PuzzlesIndex {
  aoc: { years: AocYear[] };
  euler: { publishLimit: number; solved: EulerSummary[] };
}

export interface AocYear {
  year: number;
  /** 25 up to 2024, 12 from 2025. */
  totalDays: number;
  solutions: AocDaySummary[];
}

export interface AocDaySummary {
  day: number;
  /** 1 or 2: days with neither part solved aren't exported. */
  stars: number;
  title: string | null;
}

export interface EulerSummary {
  problem: number;
  title: string | null;
}

export interface AocPart {
  part: 1 | 2;
  solved: boolean;
  /** 1-based line range of `def part_N` within `source`; absent if it isn't defined. */
  startLine?: number;
  endLine?: number;
}

/** A solution as the modal shows it, from either collection. */
export interface PuzzleSolution {
  title: string | null;
  /** Further paragraphs of the module docstring, if any. */
  description: string | null;
  problemUrl: string;
  /** The Python source, with the module docstring taken off. */
  source: string;
}

export interface AocSolution extends PuzzleSolution {
  year: number;
  day: number;
  stars: number;
  parts: AocPart[];
}

export interface EulerSolution extends PuzzleSolution {
  problem: number;
}
