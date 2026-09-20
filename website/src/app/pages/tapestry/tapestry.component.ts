import { Component, OnDestroy, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { forkJoin } from 'rxjs';
import { TapestryService } from '../../core/services/tapestry.service';
import { TapestryGeometry, TapestryStory } from '../../core/models/tapestry.interface';

/** One day's panel, ready to render (SVG turned into a Blob object URL). */
interface PanelView {
  date: string;
  generatedAt: string;
  /** Full OpenRouter model id (e.g. "moonshotai/kimi-k2.7-code"). */
  model: string;
  /** Short display label for the model (id without its vendor prefix). */
  modelLabel: string;
  /** The model's reasoning for the day, or null if none was recorded. */
  plan: string | null;
  stories: TapestryStory[];
  svgUrl: SafeUrl;
}

const DEFAULT_GEOMETRY: TapestryGeometry = { panel_width: 1600, panel_height: 200, overlap: 40 };

@Component({
  selector: 'app-tapestry',
  standalone: true,
  imports: [DatePipe],
  template: `
    <div class="tapestry">
      <header class="intro">
        <h1>News Tapestry</h1>
        <p>
          A Bayeux-style tapestry of the day's news, woven one panel at a time.
          Each morning three top stories are handed to a model that illustrates
          them as a single continuous scene with SVG elements, which then "stitches" it into the day
          before. It grows downward, so the newest section is at the bottom.
        </p>
        @if (panels().length) {
          <button type="button" class="jump" (click)="jumpToLatest()">
            Jump to latest ({{ panels()[panels().length - 1].date | date:'mediumDate' }}) &darr;
          </button>
        }
      </header>

      @if (loading()) {
        <p class="status">Weaving&hellip;</p>
      } @else if (error()) {
        <p class="status">Couldn't load the tapestry right now. Please try again later.</p>
      } @else if (!panels().length) {
        <p class="status">The tapestry hasn't been started yet. Check back tomorrow.</p>
      } @else {
        <!-- One grid row per day: the tapestry section (col 1) and its terse
             story details (col 2) sit side by side. The art cell is exactly one
             "step" tall (panel_height - overlap); its <img> is a full panel and
             so overflows downward by the overlap, which the next (newer) row
             paints over — that's what keeps the seam invisible. -->
        <div class="layout"
             [style.--panel-w]="geo().panel_width"
             [style.--step]="step()"
             [style.--n]="panels().length">
          @for (panel of panels(); track panel.date; let i = $index) {
            <div class="day-model" [style.--i]="i">
              <div class="inner">
                <span class="model" tabindex="0">
                  <span class="model-label">Drawn by</span>
                  <span class="model-name">{{ panel.modelLabel }}</span>
                  <span class="tip model-tip">
                    <span class="tip-title">{{ panel.model }}</span>
                    @if (panel.plan) {
                      <span class="tip-summary plan">{{ panel.plan }}</span>
                    } @else {
                      <span class="tip-summary muted">No reasoning was recorded for this day.</span>
                    }
                  </span>
                </span>
              </div>
            </div>
            <div class="day-art" [id]="'panel-' + panel.date" [style.--i]="i">
              <img [src]="panel.svgUrl" [alt]="'News tapestry panel for ' + panel.date">
            </div>
            <div class="day-stories" [style.--i]="i">
              <div class="inner">
                <span class="day-date">{{ panel.date | date:'MMM d' }}</span>
                @for (story of panel.stories; track story.link) {
                  <span class="story">
                    <a [href]="story.link" target="_blank" rel="noopener noreferrer">{{ story.title }}</a>
                    <span class="tip">
                      <span class="tip-title">{{ story.title }}</span>
                      @if (story.summary) {
                        <span class="tip-summary">{{ story.summary }}</span>
                      }
                    </span>
                  </span>
                }
              </div>
            </div>
          }
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .tapestry {
      max-width: 1240px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }

    .intro h1 {
      margin-bottom: 0.75rem;
    }

    .intro p {
      color: #6b7280;
      max-width: 46rem;
      line-height: 1.55;
    }

    .jump {
      margin-top: 1rem;
      background: none;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 0.4rem 0.75rem;
      color: #6b7280;
      font: inherit;
      font-size: 0.875rem;
      cursor: pointer;
      transition: color 0.2s, border-color 0.2s;
    }

    .jump:hover {
      color: #0f1219;
      border-color: #9ca3af;
    }

    .status {
      color: #6b7280;
      padding: 2rem 0;
    }

    .layout {
      display: grid;
      grid-template-columns: 116px minmax(0, 1fr) 240px;
      column-gap: 1.5rem;
      align-items: stretch;
      margin-top: 2rem;
    }

    /* The tapestry section: one step tall, the <img> overflows by the overlap. */
    .day-art {
      position: relative;
      grid-column: 2;
      grid-row: calc(var(--i) + 1);
      aspect-ratio: var(--panel-w) / var(--step);
    }

    .day-art img {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: auto;
      display: block;
    }

    /* Terse story details, aligned to their section. Absolutely-filled so their
       height can never grow the grid row (which would open a seam). */
    .day-stories {
      position: relative;
      grid-column: 3;
      grid-row: calc(var(--i) + 1);
    }

    .day-stories .inner,
    .day-model .inner {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
    }

    .day-model .inner {
      justify-content: center;
      gap: 0.15rem;
    }

    /* The date + three headlines are distributed across the full panel height so
       the column keeps the same vertical rhythm as the woven strip beside it,
       rather than clustering in the middle (which crowds the next day's text). */
    .day-stories .inner {
      justify-content: space-between;
      padding: 0.05rem 0 0.15rem;
    }

    /* Left column: which model drew this day's panel, with its reasoning on
       hover. Mirrors .day-stories (absolutely-filled so it can't grow the row
       and open a seam). */
    .day-model {
      position: relative;
      grid-column: 1;
      grid-row: calc(var(--i) + 1);
    }

    .day-model .inner {
      align-items: flex-start;
      text-align: left;
    }

    .model {
      position: relative;
      display: inline-flex;
      flex-direction: column;
      gap: 0.05rem;
      cursor: help;
      outline: none;
    }

    .model-label {
      font-size: 0.62rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #9ca3af;
    }

    .model-name {
      font-size: 0.78rem;
      line-height: 1.3;
      color: #6b7280;
      word-break: break-word;
      border-bottom: 1px dotted #cbd5e1;
    }

    .model:hover .model-name,
    .model:focus .model-name {
      color: #0f1219;
      border-bottom-color: #9ca3af;
    }

    /* The reasoning tip is wider than a story tip and can hold a paragraph. */
    .model-tip {
      width: min(340px, 80vw);
    }

    .model:hover .tip,
    .model:focus .tip {
      display: block;
    }

    .tip-summary.plan {
      display: block;
      -webkit-line-clamp: unset;
      max-height: 42vh;
      overflow-y: auto;
      white-space: pre-wrap;
    }

    .tip-summary.muted {
      color: #9ca3af;
      font-style: italic;
    }

    .day-date {
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #9ca3af;
      margin-bottom: 0.1rem;
    }

    .story {
      position: relative;
    }

    .story > a {
      display: block;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: 0.8rem;
      line-height: 1.25;
      color: #6b7280;
      text-decoration: none;
    }

    .story:hover > a {
      color: #0f1219;
    }

    /* Hover reveal: absolutely positioned so it floats over everything without
       affecting layout. */
    .tip {
      display: none;
      position: absolute;
      left: 0;
      top: 100%;
      z-index: 30;
      width: max(240px, 100%);
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
      padding: 0.6rem 0.7rem;
    }

    .story:hover .tip,
    .story:focus-within .tip {
      display: block;
    }

    .tip-title {
      display: block;
      font-size: 0.8rem;
      font-weight: 600;
      line-height: 1.35;
      color: #0f1219;
      margin-bottom: 0.35rem;
    }

    .tip-summary {
      display: -webkit-box;
      -webkit-line-clamp: 5;
      -webkit-box-orient: vertical;
      overflow: hidden;
      font-size: 0.75rem;
      line-height: 1.45;
      color: #6b7280;
    }

    /* Narrow screens: the panels are far too short to align stories beside them,
       so the seamless ribbon runs full-width (overlap preserved) and every day's
       stories flow in a date-labelled list below it. Explicit grid rows move the
       story blocks from column 2 down to rows after the whole ribbon. */
    @media (max-width: 720px) {
      .tapestry {
        padding: 2rem 1rem;
      }

      .layout {
        grid-template-columns: 1fr;
        column-gap: 0;
      }

      .day-art {
        grid-column: 1;
      }

      /* Below the full-width ribbon each day gets two stacked rows: its model
         note, then its stories. (Rows n+1 .. n+2n, interleaved per day.) */
      .day-model {
        grid-column: 1;
        grid-row: calc(var(--n) + 2 * var(--i) + 1);
        margin-top: 1.5rem;
      }

      .day-model .inner {
        position: static;
      }

      .day-model .model {
        flex-direction: row;
        align-items: baseline;
        gap: 0.4rem;
        cursor: default;
      }

      .day-stories {
        grid-column: 1;
        grid-row: calc(var(--n) + 2 * var(--i) + 2);
        margin-top: 0.4rem;
      }

      .day-stories .inner {
        position: static;
        gap: 0.35rem;
      }

      .tip-summary.plan {
        max-height: none;
        overflow: visible;
      }

      .story > a {
        white-space: normal;
        font-size: 0.9rem;
      }

      .tip {
        position: static;
        display: block;
        margin-top: 0.25rem;
        box-shadow: none;
        border: none;
        padding: 0;
        width: auto;
      }

      .tip-title {
        display: none;
      }

      .tip-summary {
        -webkit-line-clamp: 2;
      }
    }
  `]
})
export class TapestryComponent implements OnInit, OnDestroy {
  private tapestry = inject(TapestryService);
  private sanitizer = inject(DomSanitizer);

  panels = signal<PanelView[]>([]);
  loading = signal(true);
  error = signal(false);

  private geometry = signal<TapestryGeometry | null>(null);
  /** Geometry with a fallback, so the CSS custom properties are always valid. */
  geo = computed(() => this.geometry() ?? DEFAULT_GEOMETRY);
  /** Per-day vertical advance in px; the art cell's height (before overlap). */
  step = computed(() => this.geo().panel_height - this.geo().overlap);

  private objectUrls: string[] = [];

  ngOnInit(): void {
    this.tapestry.getIndex().subscribe({
      next: index => {
        this.geometry.set(index.geometry);
        if (!index.dates.length) {
          this.loading.set(false);
          return;
        }
        // Fetch every panel; the manifest already lists them oldest-first, which
        // is the order the seams were designed to join in.
        forkJoin(index.dates.map(date => this.tapestry.getPanel(date))).subscribe({
          next: fetched => {
            this.panels.set(fetched.map(p => ({
              date: p.date,
              generatedAt: p.generated_at,
              model: p.model,
              modelLabel: this.toModelLabel(p.model),
              plan: p.plan ?? null,
              stories: p.stories ?? [],
              svgUrl: this.toSvgUrl(p.svg),
            })));
            this.loading.set(false);
          },
          error: () => this.fail(),
        });
      },
      error: () => this.fail(),
    });
  }

  ngOnDestroy(): void {
    this.objectUrls.forEach(url => URL.revokeObjectURL(url));
  }

  jumpToLatest(): void {
    const list = this.panels();
    if (list.length) {
      this.scrollTo(list[list.length - 1].date);
    }
  }

  scrollTo(date: string): void {
    document.getElementById(`panel-${date}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /** Short label for a model id: drop the "vendor/" prefix so the narrow left
   *  column shows e.g. "kimi-k2.7-code" rather than "moonshotai/kimi-k2.7-code".
   *  The full id is still shown in the hover tip. */
  private toModelLabel(model: string): string {
    const slash = model.indexOf('/');
    return slash === -1 ? model : model.slice(slash + 1);
  }

  /** Wrap a raw SVG string as an <img>-loadable Blob URL. Loading each panel as
   *  an image isolates its markup, so ids (gradients, patterns) can't collide
   *  across days and no embedded script can run. */
  private toSvgUrl(svg: string): SafeUrl {
    const blob = new Blob([svg], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    this.objectUrls.push(url);
    return this.sanitizer.bypassSecurityTrustUrl(url);
  }

  private fail(): void {
    this.error.set(true);
    this.loading.set(false);
  }
}
