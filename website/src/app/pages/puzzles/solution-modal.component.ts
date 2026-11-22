import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Location } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { catchError, map, of, startWith, switchMap } from 'rxjs';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import { PuzzlesService } from '../../core/services/puzzles.service';
import { StarsComponent } from '../../shared/components/stars/stars.component';
import { AocPart, AocSolution, EulerSolution, PuzzlesIndex } from '../../core/models/puzzles.interface';

type Kind = 'aoc' | 'euler';

/** One solution's place in the overview, as a router path under /puzzles. */
type Key = (string | number)[];

interface View {
  title: string | null;
  description: string | null;
  problemUrl: string;
  lines: string[];
  parts: AocPart[];
  stars: number;
}

/** Router state carried by links from the overview, so closing can go back to it. */
const FROM_OVERVIEW = { fromOverview: true };

/**
 * Splits Prism's highlighted HTML into lines. A token can span lines (a multi-line
 * string), so any span still open at a newline is closed there and reopened on the
 * next line, keeping every line well-formed on its own.
 */
function highlightLines(source: string): string[] {
  const html = Prism.highlight(source, Prism.languages['python'], 'python');
  const lines: string[] = [];
  const open: string[] = [];
  let line = '';
  for (const [, opening, closing, newline, text] of html.matchAll(
    /(<span[^>]*>)|(<\/span>)|(\n)|([^<\n]+)/g,
  )) {
    if (opening) {
      open.push(opening);
      line += opening;
    } else if (closing) {
      open.pop();
      line += closing;
    } else if (newline) {
      lines.push(line + '</span>'.repeat(open.length));
      line = open.join('');
    } else {
      line += text;
    }
  }
  if (line.replace(/<[^>]+>/g, '') !== '') lines.push(line);
  return lines;
}

@Component({
  selector: 'app-solution-modal',
  standalone: true,
  imports: [StarsComponent],
  template: `
    <div class="overlay" (click)="close()">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="solution-heading"
           tabindex="-1" #dialog (click)="$event.stopPropagation()">
        <header>
          <div class="titles">
            <h2 id="solution-heading">
              {{ heading() }}
              @if (view(); as v) { <app-stars [count]="v.stars" /> }
            </h2>
            @if (view()?.title; as title) { <p class="title">{{ title }}</p> }
          </div>
          <nav class="controls" aria-label="Solution">
            <button type="button" (click)="step(-1)" [disabled]="!prev()" aria-label="Previous solution">&larr;</button>
            <button type="button" (click)="step(1)" [disabled]="!next()" aria-label="Next solution">&rarr;</button>
            <button type="button" (click)="close()" aria-label="Close">&times;</button>
          </nav>
        </header>

        @if (view(); as v) {
          <div class="meta">
            <a [href]="v.problemUrl" target="_blank" rel="noopener">View the problem</a>
            @for (p of v.parts; track p.part) {
              @if (p.startLine) {
                <button type="button" class="part" [class.active]="part() === p.part"
                        [attr.aria-pressed]="part() === p.part" (click)="showPart(p.part)">
                  Part {{ p.part }}
                </button>
              }
            }
          </div>
          @if (v.description) { <p class="description">{{ v.description }}</p> }
          <pre class="language-python" #code><code>@for (line of v.lines; track $index) {<span
            class="line" [class.in-part]="inPart($index + 1)" [innerHTML]="line || ' '"></span>}</code></pre>
        } @else if (failed()) {
          <p class="status">That solution couldn't be loaded.</p>
        } @else {
          <p class="status">Loading…</p>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  host: {
    '(document:keydown.escape)': 'close()',
    '(document:keydown.arrowleft)': 'step(-1)',
    '(document:keydown.arrowright)': 'step(1)',
  },
  styles: [`
    .overlay {
      position: fixed;
      inset: 0;
      background: rgba(15, 18, 25, 0.55);
      z-index: 200;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .modal {
      background: var(--color-white);
      border-radius: 10px;
      width: 100%;
      max-width: 880px;
      max-height: 100%;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      outline: none;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      padding: 1rem 1.25rem 0.5rem;
    }
    h2 { font-size: 1.15rem; }
    .title { color: var(--color-gray); margin: 0; font-size: 0.9rem; }
    h2 .stars { font-size: 0.85rem; margin-left: 0.3em; }
    .controls { display: flex; gap: 0.25rem; flex: none; }
    button {
      font: inherit;
      background: none;
      border: 1px solid var(--color-gray-light);
      border-radius: 6px;
      color: var(--color-black);
      cursor: pointer;
      padding: 0.1rem 0.6rem;
    }
    button:hover:not(:disabled) { border-color: var(--color-black); }
    button:disabled { color: var(--color-gray-light); cursor: default; }
    .meta {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
      padding: 0 1.25rem 0.75rem;
      font-size: 0.85rem;
    }
    .meta a { color: var(--color-gray); margin-right: auto; }
    .part { font-size: 0.8rem; }
    .part.active { border-color: var(--color-gold); color: var(--color-gold); }
    .description {
      padding: 0 1.25rem;
      color: var(--color-gray);
      font-size: 0.9rem;
      white-space: pre-line;
    }
    pre[class*='language-'] {
      margin: 0;
      border-radius: 0;
      flex: 1;
      overflow: auto;
      padding: 0.75rem 0;
      font-size: 0.8rem;
      counter-reset: line;
    }
    code { display: block; width: max-content; min-width: 100%; font-family: var(--font-family); }
    .line { display: block; padding: 0 1.25rem 0 0.5rem; }
    .line::before {
      counter-increment: line;
      content: counter(line);
      display: inline-block;
      width: 2.5em;
      margin-right: 1em;
      text-align: right;
      color: #6b7280;
    }
    .line.in-part { background: rgba(255, 255, 255, 0.06); box-shadow: inset 3px 0 var(--color-gold); }
    .status { padding: 2rem 1.25rem; color: var(--color-gray); text-align: center; }

    @media (max-width: 600px) {
      .overlay { padding: 0; }
      .modal { border-radius: 0; height: 100%; max-width: none; }
    }
  `],
})
export class SolutionModalComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private location = inject(Location);
  private puzzles = inject(PuzzlesService);

  private dialog = viewChild<ElementRef<HTMLElement>>('dialog');
  private code = viewChild<ElementRef<HTMLElement>>('code');

  readonly part = signal<1 | 2 | null>(null);
  readonly failed = signal(false);

  private readonly kind: Kind = this.route.snapshot.data['kind'];
  private readonly params = toSignal(this.route.paramMap, { requireSync: true });
  private readonly index = toSignal(this.puzzles.getIndex().pipe(catchError(() => of(null))), {
    initialValue: null as PuzzlesIndex | null,
  });

  /** The current solution's router key, e.g. ['aoc', 2025, 7] or ['euler', 12]. */
  private readonly key = computed<Key>(() => {
    const p = this.params();
    return this.kind === 'aoc'
      ? ['aoc', Number(p.get('year')), Number(p.get('day'))]
      : ['euler', Number(p.get('problem'))];
  });

  readonly view = toSignal(
    this.route.paramMap.pipe(
      switchMap(() => {
        this.failed.set(false);
        this.part.set(null);
        const [, a, b] = this.key();
        const request =
          this.kind === 'aoc'
            ? this.puzzles.getAocSolution(a as number, b as number).pipe(map((s) => this.aocView(s)))
            : this.puzzles.getEulerSolution(a as number).pipe(map((s) => this.eulerView(s)));
        return request.pipe(
          startWith(null),
          catchError(() => {
            this.failed.set(true);
            return of(null);
          }),
        );
      }),
    ),
    { initialValue: null },
  );

  /**
   * The solved tiles of this collection in the order the overview shows them (AoC
   * newest year first, days ascending; Euler ascending). ← / → step through it.
   */
  private readonly order = computed<Key[]>(() => {
    const index = this.index();
    if (!index) return [];
    const aoc = [...(index.aoc?.years ?? [])]
      .sort((a, b) => b.year - a.year)
      .flatMap((y) => (y.solutions ?? []).map((s): Key => ['aoc', y.year, s.day]));
    const euler = (index.euler?.solved ?? []).map((p): Key => ['euler', p.problem]);
    return this.kind === 'aoc' ? aoc : euler;
  });

  readonly heading = computed(() => {
    const [, a, b] = this.key();
    return this.kind === 'aoc' ? `${a} · Day ${b}` : `Problem ${a}`;
  });

  private readonly position = computed(() => {
    const here = this.key().join('/');
    return this.order().findIndex((k) => k.join('/') === here);
  });
  readonly prev = computed(() => (this.position() > 0 ? this.order()[this.position() - 1] : null));
  readonly next = computed(() => {
    const i = this.position();
    return i >= 0 && i < this.order().length - 1 ? this.order()[i + 1] : null;
  });

  private previousOverflow = '';

  ngOnInit(): void {
    this.previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    queueMicrotask(() => this.dialog()?.nativeElement.focus());
  }

  ngOnDestroy(): void {
    document.body.style.overflow = this.previousOverflow;
  }

  close(): void {
    // Opened from a tile: going back restores the overview's history entry (and the
    // browser's back button does the same). Opened from a shared link: there's no
    // overview behind us, so navigate to it instead of leaving the site.
    if (history.state?.fromOverview) {
      this.location.back();
    } else {
      this.router.navigate(['/puzzles']);
    }
  }

  step(direction: -1 | 1): void {
    const target = direction < 0 ? this.prev() : this.next();
    if (!target) return;
    // replaceUrl, so stepping through solutions doesn't pile up history: one back
    // still closes the modal. The overview marker is carried over.
    this.router.navigate(['/puzzles', ...target], {
      replaceUrl: true,
      state: history.state?.fromOverview ? FROM_OVERVIEW : {},
    });
  }

  inPart(line: number): boolean {
    const part = this.view()?.parts.find((p) => p.part === this.part());
    return !!part?.startLine && line >= part.startLine && line <= (part.endLine ?? part.startLine);
  }

  showPart(part: 1 | 2): void {
    if (this.part() === part) {
      this.part.set(null);
      return;
    }
    this.part.set(part);
    const start = this.view()?.parts.find((p) => p.part === part)?.startLine;
    const line = start ? this.code()?.nativeElement.querySelectorAll('.line')[start - 1] : null;
    line?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  private aocView(s: AocSolution): View {
    return {
      title: s.title ?? null,
      description: s.description ?? null,
      problemUrl: s.problemUrl,
      lines: highlightLines(s.source ?? ''),
      parts: s.parts ?? [],
      stars: s.stars ?? 0,
    };
  }

  private eulerView(s: EulerSolution): View {
    return {
      title: s.title ?? null,
      description: s.description ?? null,
      problemUrl: s.problemUrl,
      lines: highlightLines(s.source ?? ''),
      parts: [],
      stars: 1,
    };
  }
}

