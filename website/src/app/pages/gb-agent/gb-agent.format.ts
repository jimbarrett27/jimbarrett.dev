import {
  GbAgentActivity, GbAgentClip, GbAgentMon, GbAgentState,
} from '../../core/models/gb-agent.interface';

/** One model turn in the log: what it said, what it called, what came back. */
export interface LogTurn {
  key: string;
  text: string | null;
  calls: string[];
  results: LogResult[];
}

export interface LogResult {
  text: string;
  /** good: the screen changed; warn: it barely did; bad: the step failed; info: not a step. */
  tone: 'good' | 'warn' | 'bad' | 'info';
}

function parse(json: string | null | undefined): unknown {
  if (!json) return null;
  try {
    return JSON.parse(json);
  } catch {
    return null;  // trimmed by the publisher, so possibly cut mid-way
  }
}

function value(v: unknown): string {
  const s = typeof v === 'string' ? `"${v}"` : JSON.stringify(v);
  return s.length > 40 ? s.slice(0, 39) + '…' : s;
}

function kwargs(args: unknown): string {
  if (!args || typeof args !== 'object') return '';
  return Object.entries(args).map(([k, v]) => `${k}=${value(v)}`).join(', ');
}

/** `walk(direction="left", steps=2)` from a script name and its JSON args. */
export function scriptCall(script: string | null | undefined, args: string | null | undefined): string {
  if (!script) return 'one-off code';
  return `${script}(${kwargs(parse(args))})`;
}

/** A tool call as the log shows it; run_script shows the script itself. */
export function formatCall(name: string, argsJson: string | null | undefined): string {
  const args = parse(argsJson) as Record<string, unknown> | null;
  if (name === 'run_script' && typeof args?.['name'] === 'string') {
    return `${args['name']}(${kwargs(args['args'])})`;
  }
  if (name === 'update_notes') return 'update_notes(…)';
  if ((name === 'write_script' || name === 'test_script') && typeof args?.['name'] === 'string') {
    return `${name}("${args['name']}", …)`;
  }
  if (name === 'run_code' || name === 'test_code') return `${name}(…)`;
  return `${name}(${kwargs(args)})`;
}

/** "ok · 32 frames · most of the screen changed" from a step's trace text. */
export function summarizeResult(result: string | null | undefined): LogResult {
  const text = result ?? '';
  const first = text.split('\n', 1)[0];
  const frames = text.match(/\((\d+) used\)/)?.[1];
  if (!frames) {
    return { text: first.length > 90 ? first.slice(0, 89) + '…' : first, tone: 'info' };
  }
  const status = first.slice(first.lastIndexOf(': ') + 2).replace(/\s*\[.*$/, '') || 'done';
  const screen = text.match(/screen: (.+?)(?: \(|\n|$)/)?.[1];
  const parts = [status, `${frames} frames`, ...(screen ? [screen] : [])];
  const tone = status !== 'ok' ? 'bad' : /tiny|nothing|didn't/.test(screen ?? '') ? 'warn' : 'good';
  return { text: parts.join(' · '), tone };
}

/** Group activity into model turns, newest first. */
export function toTurns(activity: GbAgentActivity[]): LogTurn[] {
  const turns: LogTurn[] = [];
  for (const a of activity) {
    if (a.kind === 'llm') {
      turns.push({
        key: `${a.time}`,
        text: a.text || a.reasoning || null,
        calls: (a.tool_calls ?? []).map(c => formatCall(c.name, c.args)),
        results: [],
      });
    } else if (a.kind === 'tool') {
      const result = summarizeResult(a.result);
      if (turns.length) turns[turns.length - 1].results.push(result);
      else turns.push({ key: `${a.time}`, text: null, calls: [formatCall(a.tool ?? '?', a.args)], results: [result] });
    } else if (a.kind === 'compaction') {
      turns.push({ key: `${a.time}`, text: null, calls: [], results: [
        { text: 'context full: cleared, keeping only its notes', tone: 'info' }] });
    }
  }
  return turns.reverse();
}

function escape(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** The agent's markdown-ish notes as safe HTML: paragraphs, **bold** and `code`. */
export function notesHtml(notes: string): string {
  return notes.trim().split(/\n\s*\n/).map(p => '<p>' + escape(p)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>') + '</p>').join('');
}

/** Game time as m:ss (or h:mm:ss) from a frame count. */
export function gameTime(frame: number | undefined, fps = 60): string {
  const s = Math.floor((frame ?? 0) / fps);
  const mmss = `${Math.floor(s / 60) % 60}:${String(s % 60).padStart(2, '0')}`;
  return s >= 3600 ? `${Math.floor(s / 3600)}:${mmss.padStart(5, '0')}` : mmss;
}

/** Clips with the game state each one ends on: the publisher only lists a state
 *  where it changed, so carry the last one forward. */
export function withState(clips: GbAgentClip[]): GbAgentClip[] {
  let state: GbAgentState | null | undefined;
  return clips.map(c => {
    if (c.state !== undefined) {
      state = c.state;
      return c;
    }
    return state === undefined ? c : { ...c, state };
  });
}

/** The Pokémon's Gen 2 sprite, by national Pokédex number. */
export function spriteUrl(dex: number | undefined): string | null {
  return dex && dex > 0 && dex <= 251
    ? `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-ii/silver/${dex}.png`
    : null;
}

/** "PIDGE (Pidgey)", or just "Cyndaquil" when it was never nicknamed. */
export function monName(m: GbAgentMon): string {
  const nick = m.nickname?.trim();
  return !nick || nick.toUpperCase() === m.species.toUpperCase() ? m.species : `${nick} (${m.species})`;
}

/** HP left as a percentage and a colour, as the game's own bar turns yellow then red. */
export function hpBar(m: GbAgentMon): { percent: number; tone: 'good' | 'warn' | 'bad' } {
  const percent = m.max_hp ? Math.max(0, Math.min(100, 100 * (m.hp ?? 0) / m.max_hp)) : 0;
  return { percent, tone: percent > 50 ? 'good' : percent > 20 ? 'warn' : 'bad' };
}

export type TileKind = 'floor' | 'wall' | 'water' | 'grass' | 'ledge' | 'off';

/** A horizontal run of tiles of one kind, so a map draws as a few rects, not one per tile. */
export interface TileRun {
  x: number;
  y: number;
  width: number;
  kind: TileKind;
}

function tileKind(c: string): TileKind {
  switch (c) {
    case '.': return 'floor';
    case '#': return 'wall';
    case '~': return 'water';
    case 'g': return 'grass';
    case 'v': case '<': case '>': return 'ledge';
    default: return 'off';
  }
}

export function tileRuns(rows: string[]): TileRun[] {
  const runs: TileRun[] = [];
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length;) {
      const kind = tileKind(row[x]);
      let end = x + 1;
      while (end < row.length && tileKind(row[end]) === kind) end++;
      runs.push({ x, y, width: end - x, kind });
      x = end;
    }
  });
  return runs;
}
