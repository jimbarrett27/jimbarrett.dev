import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink, RouterOutlet } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { PuzzlesService } from '../../core/services/puzzles.service';
import { StarsComponent } from '../../shared/components/stars/stars.component';
import { AocYear, PuzzlesIndex } from '../../core/models/puzzles.interface';

interface Tile {
  n: number;
  stars: number;
  title: string | null;
  today: boolean;
}

interface YearCard {
  year: number;
  totalDays: number;
  stars: number;
  live: boolean;
  tiles: Tile[];
}

const aocDaysInYear = (year: number) => (year >= 2025 ? 12 : 25);

@Component({
  selector: 'app-puzzles',
  standalone: true,
  imports: [RouterLink, RouterOutlet, StarsComponent],
  template: `
    <div class="puzzles">
      <h1>Puzzles</h1>
      <p class="intro">
        My solutions to <a href="https://adventofcode.com" target="_blank" rel="noopener">Advent of Code</a>
        and <a href="https://projecteuler.net" target="_blank" rel="noopener">Project Euler</a>, in Python.
        Pick a solved tile to read the code.
      </p>

      @if (error()) {
        <p class="note">The puzzles couldn't be loaded. Try refreshing the page.</p>
      } @else if (index()) {
        <h2>Advent of Code</h2>
        <p class="summary"><span class="gold">{{ aocStars() }}<app-stars /></span> across {{ years().length }} years</p>
        <div class="years">
          @for (card of years(); track card.year) {
            <section class="card" [attr.aria-label]="'Advent of Code ' + card.year">
              <h3>
                {{ card.year }} <span class="gold">{{ card.stars }}<app-stars /></span>
                <span class="of">of {{ card.totalDays * 2 }}</span>
                @if (card.live) { <span class="live">in progress</span> }
              </h3>
              <div class="grid cal">
                @for (t of card.tiles; track t.n) {
                  @if (t.stars) {
                    <a class="tile solved" [class.today]="t.today" [routerLink]="['aoc', card.year, t.n]" [state]="fromOverview"
                       [title]="t.title ?? 'Day ' + t.n"
                       [attr.aria-label]="'Day ' + t.n + ', ' + t.stars + (t.stars === 1 ? ' star' : ' stars')">
                      {{ t.n }}<app-stars [count]="t.stars" />
                    </a>
                  } @else {
                    <span class="tile" [class.today]="t.today">{{ t.n }}</span>
                  }
                }
              </div>
            </section>
          }
        </div>

        <h2>Project Euler</h2>
        <p class="summary">
          <span class="gold">{{ euler().length }}<app-stars /></span> of the first {{ eulerLimit() }}
          <span class="aside">· Project Euler asks that only these are shared</span>
        </p>
        <section class="card" aria-label="Project Euler">
          <div class="grid hundred">
            @for (t of eulerTiles(); track t.n) {
              @if (t.stars) {
                <a class="tile solved" [routerLink]="['euler', t.n]" [state]="fromOverview" [title]="t.title ?? 'Problem ' + t.n"
                   [attr.aria-label]="'Problem ' + t.n">
                  {{ t.n }}<app-stars />
                </a>
              } @else {
                <span class="tile">{{ t.n }}</span>
              }
            }
          </div>
        </section>
      }
    </div>

    <router-outlet />
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .puzzles { max-width: var(--max-width-wide); margin: 0 auto; padding: 2rem 1rem 3rem; }
    h1 { margin-bottom: 0.5rem; }
    h2 { margin: 2.5rem 0 0.25rem; }
    .intro { color: var(--color-gray); max-width: var(--max-width); }
    .intro a { color: inherit; }
    .note, .summary, .of, .aside { color: var(--color-gray); }
    .summary { font-size: 0.9rem; }
    .aside, .of { font-size: 0.8rem; }
    /* Angular drops whitespace-only text between elements, so space them here. */
    .gold + .of, .of + .live { margin-left: 0.4em; }
    .gold { color: var(--color-gold); }

    .years {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 1.25rem;
    }
    .card {
      border: 1px solid var(--color-gray-light);
      border-radius: 10px;
      padding: 0.9rem 1rem 1rem;
      width: fit-content;
      max-width: 100%;
    }
    .years .card { width: auto; }
    h3 { font-size: 1rem; font-weight: 400; margin-bottom: 0.5rem; }
    .live {
      font-size: 0.7rem;
      border: 1px solid var(--color-gold);
      color: var(--color-gold);
      border-radius: 999px;
      padding: 0 0.5rem;
      margin-left: 0.25rem;
    }

    .grid { display: grid; gap: 4px; --tile: 32px; }
    .cal { grid-template-columns: repeat(7, var(--tile)); }
    .hundred { grid-template-columns: repeat(10, var(--tile)); }
    .tile {
      width: var(--tile);
      height: var(--tile);
      border: 1px solid var(--color-gray-light);
      border-radius: 6px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 0.7rem;
      line-height: 1;
      color: var(--color-gray);
      text-decoration: none;
    }
    .tile.solved { border-color: var(--color-black); color: var(--color-black); transition: transform 0.15s; }
    .tile.solved:hover, .tile.solved:focus-visible { transform: translateY(-2px); background: var(--color-gray-lighter); }
    .tile.today { outline: 2px solid var(--color-gold); outline-offset: 1px; }
    .tile .stars { font-size: 0.6rem; margin-top: 3px; }

    @media (max-width: 380px) {
      .grid { --tile: 28px; }
    }
  `],
})
export class PuzzlesComponent {
  private puzzles = inject(PuzzlesService);

  /** Router state the modal reads to know closing can go back to this page. */
  readonly fromOverview = { fromOverview: true };

  readonly error = signal(false);
  readonly index = toSignal(
    this.puzzles.getIndex().pipe(
      map((index): PuzzlesIndex | null => index),
      catchError(() => {
        this.error.set(true);
        return of(null);
      }),
    ),
    { initialValue: null },
  );

  private readonly now = new Date();

  readonly years = computed<YearCard[]>(() => {
    const years: AocYear[] = [...(this.index()?.aoc?.years ?? [])];

    // During December the current year gets a card (with today's door marked)
    // even before anything is solved, so the page reflects a year in progress.
    const thisYear = this.now.getFullYear();
    const inDecember = this.now.getMonth() === 11;
    if (inDecember && !years.some((y) => y.year === thisYear)) {
      years.unshift({ year: thisYear, totalDays: aocDaysInYear(thisYear), solutions: [] });
    }

    return years
      .sort((a, b) => b.year - a.year)
      .map((y) => {
        const live = inDecember && y.year === thisYear && this.now.getDate() <= y.totalDays;
        const solved = new Map((y.solutions ?? []).map((s) => [s.day, s]));
        const tiles = Array.from({ length: y.totalDays }, (_, i): Tile => {
          const s = solved.get(i + 1);
          return {
            n: i + 1,
            stars: s?.stars ?? 0,
            title: s?.title ?? null,
            today: live && this.now.getDate() === i + 1,
          };
        });
        return {
          year: y.year,
          totalDays: y.totalDays,
          stars: tiles.reduce((sum, t) => sum + t.stars, 0),
          live,
          tiles,
        };
      });
  });

  readonly aocStars = computed(() => this.years().reduce((sum, y) => sum + y.stars, 0));

  readonly eulerLimit = computed(() => this.index()?.euler?.publishLimit ?? 100);
  readonly euler = computed(() => this.index()?.euler?.solved ?? []);
  readonly eulerTiles = computed<Tile[]>(() => {
    const solved = new Map(this.euler().map((p) => [p.problem, p]));
    return Array.from({ length: this.eulerLimit() }, (_, i) => {
      const p = solved.get(i + 1);
      return { n: i + 1, stars: p ? 1 : 0, title: p?.title ?? null, today: false };
    });
  });
}
