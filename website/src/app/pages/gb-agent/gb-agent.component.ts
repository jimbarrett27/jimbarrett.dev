import {
  ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal,
} from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, exhaustMap, fromEvent, map, merge, of, switchMap, timer } from 'rxjs';
import { GbAgentService } from '../../core/services/gb-agent.service';
import {
  GbAgentClip, GbAgentLive, GbAgentMap, GbAgentMon, GbAgentNotes, GbAgentOracleEntry, GbAgentScripts,
} from '../../core/models/gb-agent.interface';
import {
  gameTime, hpBar, monName, notesHtml, scriptCall, spriteUrl, toTurns, withState,
} from './gb-agent.format';
import { GbAgentMapComponent } from './gb-agent-map.component';
import { GbAgentOracleComponent } from './gb-agent-oracle.component';

const LIVE_POLL_MS = 4_000;
const IDLE_POLL_MS = 60_000;
/** The oracle writes twice a day; this only has to notice within a few minutes. */
const ORACLE_POLL_MS = 10 * 60_000;
/** A run whose manifest hasn't been written for this long is shown as offline,
 *  even if the publisher last said it was live (it may have stopped). */
const STALE_MS = 10 * 60_000;
/** If the queue gets further behind than this, skip to the newest clip. */
const MAX_BEHIND_S = 60;

/**
 * The gb_agent bot playing Pokémon, as it happens. Polls the publisher's files
 * in the bucket and plays each kept step's clip back to back at game speed,
 * next to a log of what the model said and did, its notes and its scripts, and
 * the game as it stands at the end of the clip on screen: party, trainer and map.
 */
@Component({
  selector: 'app-gb-agent',
  standalone: true,
  imports: [DecimalPipe, GbAgentMapComponent, GbAgentOracleComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './gb-agent.component.html',
  styleUrl: './gb-agent.component.css',
})
export class GbAgentComponent {
  private api = inject(GbAgentService);
  private destroyRef = inject(DestroyRef);

  readonly live = signal<GbAgentLive | null>(null);
  readonly notes = signal<GbAgentNotes | null>(null);
  readonly scripts = signal<GbAgentScripts | null>(null);
  readonly error = signal(false);
  readonly oracle = signal<GbAgentOracleEntry[]>([]);
  readonly playing = signal<GbAgentClip | null>(null);
  readonly queue = signal<GbAgentClip[]>([]);
  /** The last clip has finished and its final frame is held: the model is working. */
  readonly holding = signal(false);
  private readonly now = signal(Date.now());

  /** The newest step already played or queued; clips after it get queued. */
  private lastQueued = -1;
  private run: string | null = null;

  readonly isLive = computed(() => {
    const live = this.live();
    const updated = live?.updated_at ? Date.parse(live.updated_at) : NaN;
    return !!live?.live && this.now() - updated < STALE_MS;
  });

  readonly turns = computed(() => toTurns(this.live()?.activity ?? []));
  readonly notesHtml = computed(() => notesHtml(this.notes()?.notes ?? ''));
  readonly gameTime = computed(() => gameTime(this.live()?.frame, this.live()?.fps));
  readonly caption = computed(() => {
    const clip = this.playing();
    return clip ? `step ${clip.step} · ${scriptCall(clip.script, clip.args)}` : '';
  });

  /** The game at the end of the clip on screen, so it changes as the video does. */
  readonly game = computed(() => this.playing()?.state ?? null);
  readonly party = computed(() => (this.game()?.party ?? []).map(m => ({
    ...m, name: monName(m), sprite: spriteUrl(m.dex), bar: hpBar(m),
  })));
  readonly pos = computed(() => this.playing()?.pos ?? null);
  /** Layouts of the maps seen so far, by `pos.map`. */
  private readonly maps = signal<Record<string, GbAgentMap>>({});
  private readonly mapsAsked = new Set<string>();
  readonly map = computed(() => {
    const key = this.pos()?.map;
    return key ? this.maps()[key] ?? null : null;
  });

  /** The script whose code is shown; the most used one until a tab is picked. */
  readonly picked = signal<string | null>(null);
  readonly scriptList = computed(() => {
    const uses = this.live()?.script_uses ?? {};
    return [...(this.scripts()?.scripts ?? [])]
      .map(s => ({ ...s, uses: uses[s.name] ?? 0 }))
      .sort((a, b) => b.uses - a.uses || a.name.localeCompare(b.name));
  });
  readonly shownScript = computed(() => {
    const list = this.scriptList();
    return list.find(s => s.name === this.picked()) ?? (list.length ? list[0] : null);
  });

  /** "m:ss" the model has been working, while live and nothing is playing. */
  readonly thinkingFor = computed(() => {
    const since = this.live()?.waiting_since;
    if (!this.isLive() || (this.playing() && !this.holding()) || !since) return null;
    const s = Math.max(0, Math.floor(this.now() / 1000 - since));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  });

  constructor() {
    timer(0, 1000).pipe(takeUntilDestroyed()).subscribe(() => this.now.set(Date.now()));
    timer(0, ORACLE_POLL_MS).pipe(
      switchMap(() => this.api.getOracle().pipe(catchError(() => EMPTY))),
      takeUntilDestroyed(),
    ).subscribe(o => this.oracle.set(o.entries ?? []));

    const visible = merge(of(null), fromEvent(document, 'visibilitychange')).pipe(
      map(() => document.visibilityState === 'visible'));
    visible.pipe(
      switchMap(isVisible => isVisible
        ? timer(0, LIVE_POLL_MS).pipe(
            // Idle runs only need checking now and then.
            exhaustMap((i) => (this.isLive() || i % (IDLE_POLL_MS / LIVE_POLL_MS) === 0)
              ? this.poll() : EMPTY))
        : EMPTY),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe();
  }

  /** "◆◆◇◇◇◇◇◇" for badges won of the eight. */
  badges(n: number | null | undefined): string {
    const won = Math.max(0, Math.min(8, n ?? 0));
    return '◆'.repeat(won) + '◇'.repeat(8 - won);
  }

  movesOf(m: GbAgentMon): string {
    return (m.moves ?? []).map(mv => mv.pp !== undefined ? `${mv.name} ${mv.pp}pp` : mv.name).join(' · ');
  }

  hideImage(event: Event): void {
    (event.target as HTMLElement).style.visibility = 'hidden';
  }

  clipUrl(clip: GbAgentClip): string {
    return this.api.clipUrl(clip.key);
  }

  /** Browsers only autoplay muted video, and Angular doesn't set the `muted`
   *  property from the attribute, so start each clip by hand. */
  play(video: HTMLVideoElement): void {
    video.muted = true;
    video.play().catch(() => undefined);
  }

  /** Play the next queued clip, or hold the last frame if there isn't one. */
  next(): void {
    const [head, ...rest] = this.queue();
    if (!head) {  // keep `playing` so its last frame stays on screen
      this.holding.set(true);
      return;
    }
    this.holding.set(false);
    this.queue.set(rest);
    this.playing.set(head);
    this.loadMap(head.pos?.map);
  }

  private loadMap(key: string | undefined): void {
    const run = this.run;
    if (!key || !run || this.mapsAsked.has(key)) return;
    this.mapsAsked.add(key);
    this.api.getMap(run, key).subscribe({
      next: m => { if (this.run === run) this.maps.update(all => ({ ...all, [key]: m })); },
      // Not published yet (say the map was first seen in a battle): ask again later.
      error: () => this.mapsAsked.delete(key),
    });
  }

  private poll() {
    return this.api.getCurrent().pipe(
      switchMap(current => {
        if (current.run !== this.run) this.reset(current.run);
        return this.api.getLive(current.run);
      }),
      map(live => this.apply(live)),
      catchError(() => { this.error.set(!this.live()); return EMPTY; }),
    );
  }

  private reset(run: string): void {
    this.run = run;
    this.lastQueued = -1;
    this.queue.set([]);
    this.playing.set(null);
    this.holding.set(false);
    this.notes.set(null);
    this.scripts.set(null);
    this.picked.set(null);
    this.maps.set({});
    this.mapsAsked.clear();
  }

  private apply(live: GbAgentLive): void {
    const prev = this.live();
    this.live.set(live);
    this.error.set(false);
    const run = live.run;
    if (live.notes_version && live.notes_version !== prev?.notes_version) {
      this.api.getNotes(run).subscribe({ next: n => this.notes.set(n), error: () => undefined });
    }
    if (live.scripts_version && live.scripts_version !== prev?.scripts_version) {
      this.api.getScripts(run).subscribe({ next: s => this.scripts.set(s), error: () => undefined });
    }
    this.enqueue(withState(live.clips ?? []), live.fps ?? 60);
  }

  private enqueue(clips: GbAgentClip[], fps: number): void {
    if (!clips.length) return;
    // A newcomer starts at the newest clip rather than inheriting a backlog.
    const fresh = this.lastQueued < 0 ? clips.slice(-1) : clips.filter(c => c.step > this.lastQueued);
    if (!fresh.length) return;
    this.lastQueued = fresh[fresh.length - 1].step;
    let queue = [...this.queue(), ...fresh];
    const behind = queue.reduce((s, c) => s + (c.frames ?? 0), 0) / fps;
    if (behind > MAX_BEHIND_S) queue = queue.slice(-1);
    this.queue.set(queue);
    if (!this.playing() || this.holding()) this.next();
  }
}
