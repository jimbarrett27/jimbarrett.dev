import {
  Component,
  ElementRef,
  HostListener,
  OnDestroy,
  OnInit,
  effect,
  inject,
  signal,
  viewChildren,
  ChangeDetectionStrategy
} from '@angular/core';
import { PaperCardComponent } from '../../components/paper-card/paper-card.component';
import { ShortcutHelpComponent } from '../../components/shortcut-help/shortcut-help.component';
import { TriageApiService } from '../../services/triage-api.service';
import { Decision, Paper } from '../../models/paper.model';

type LoadState = 'loading' | 'ready' | 'error';

interface LastDecision {
  paper: Paper;
  /** Index the paper occupied in the queue, so undo can restore it in place. */
  index: number;
  decision: Decision;
}

const UNDO_WINDOW_MS = 30_000;

/**
 * Main triage view: renders the pending queue with keyboard-driven focus
 * navigation and one-keystroke decisions. Decisions persist immediately and
 * optimistically leave the queue; a decision can be undone within ~30s.
 * External routing (Zotero/Obsidian) is wired in later build steps.
 */
@Component({
  selector: 'app-triage-queue',
  standalone: true,
  imports: [PaperCardComponent, ShortcutHelpComponent],
  template: `
    <div class="queue">
      <header class="queue-head">
        <h1>Triage</h1>
        <div class="head-right">
          <div class="view-toggle">
            <button class="vt" [class.active]="view() === 'queue'" (click)="setView('queue')">
              Queue
            </button>
            <button class="vt" [class.active]="view() === 'history'" (click)="setView('history')">
              History
            </button>
          </div>
          <span class="counter">
            {{ papers().length }} {{ view() === 'queue' ? 'pending' : 'decided' }}
          </span>
          <button class="help-btn" (click)="toggleHelp()" title="Keyboard shortcuts (?)">?</button>
        </div>
      </header>

      @if (view() === 'queue' && lastDecision(); as last) {
        <p class="undo-hint">
          {{ decisionLabel(last.decision) }} “{{ last.paper.title }}” —
          <button class="link" (click)="undo()">undo</button> <kbd>u</kbd>
        </p>
      }

      @switch (state()) {
        @case ('loading') {
          <p class="status">Loading…</p>
        }
        @case ('error') {
          <p class="status error">
            Error displaying triage. If you're not Jim, this is intended. If you are Jim, go <a href="https://triage-api.jimbarrett.dev/">here</a>.
          </p>
        }
        @case ('ready') {
          @if (papers().length === 0) {
            <p class="status">
              {{ view() === 'queue' ? 'Queue empty — nothing to triage. 🎉' : 'No decisions yet.' }}
            </p>
          } @else {
            <div class="cards">
              @for (paper of papers(); track paper.id; let i = $index) {
                <app-paper-card
                  #cardEl
                  [paper]="paper"
                  [focused]="i === focusedIndex()"
                  (click)="focusedIndex.set(i)"
                  (decide)="decideOn(paper, $event)"
                  (open)="openPaper(paper)"
                />
              }
            </div>
          }
        }
      }
    </div>

    @if (showHelp()) {
      <app-shortcut-help (close)="showHelp.set(false)" />
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [
    `
      .queue {
        /* ~2/3 of the viewport on wide screens, but never narrower than the
           old 960px cap and capped so ultrawide displays stay readable. */
        width: min(1600px, max(960px, 66vw));
        max-width: 100%;
        margin: 0 auto;
        padding: 2rem 1.5rem;
      }
      .queue-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 1.5rem;
      }
      .head-right {
        display: flex;
        align-items: center;
        gap: 1rem;
      }
      .view-toggle {
        display: inline-flex;
        border: 1px solid var(--color-gray-light);
        border-radius: 6px;
        overflow: hidden;
      }
      .vt {
        font-family: var(--font-family);
        font-size: 0.85rem;
        cursor: pointer;
        padding: 0.3rem 0.75rem;
        border: none;
        background: var(--color-white);
        color: var(--color-gray);
      }
      .vt:hover {
        background: var(--color-gray-lighter);
      }
      .vt.active {
        background: var(--color-black);
        color: var(--color-white);
      }
      .counter {
        color: var(--color-gray);
        font-size: 0.9rem;
      }
      .help-btn {
        font-family: var(--font-family);
        cursor: pointer;
        width: 1.9rem;
        height: 1.9rem;
        border-radius: 50%;
        border: 1px solid var(--color-gray-light);
        background: var(--color-white);
      }
      .help-btn:hover {
        background: var(--color-gray-lighter);
      }
      .cards {
        display: flex;
        flex-direction: column;
        gap: 1rem;
      }
      .status {
        color: var(--color-gray);
      }
      .status.error {
        color: #b91c1c;
      }
      .undo-hint {
        margin: -0.5rem 0 1rem;
        padding: 0.5rem 0.75rem;
        background: var(--color-gray-lighter);
        border: 1px solid var(--color-gray-light);
        border-radius: 6px;
        font-size: 0.9rem;
        color: var(--color-gray);
      }
      .undo-hint .link {
        font-family: var(--font-family);
        font-size: inherit;
        color: var(--color-black);
        background: none;
        border: none;
        padding: 0;
        cursor: pointer;
        text-decoration: underline;
      }
      .undo-hint kbd {
        font-size: 0.75rem;
        border: 1px solid var(--color-gray-light);
        border-bottom-width: 2px;
        border-radius: 4px;
        padding: 0.05rem 0.35rem;
        background: var(--color-white);
      }
    `,
  ],
})
export class QueueComponent implements OnInit, OnDestroy {
  private api = inject(TriageApiService);

  papers = signal<Paper[]>([]);
  state = signal<LoadState>('loading');
  focusedIndex = signal(0);
  showHelp = signal(false);
  lastDecision = signal<LastDecision | null>(null);
  /** Which list is shown: the pending queue or the decided-paper history. */
  view = signal<'queue' | 'history'>('queue');

  private undoTimer: ReturnType<typeof setTimeout> | null = null;

  // `#cardEl` is on the <app-paper-card> component, so we must explicitly read
  // its host ElementRef — without `read` this returns component instances and
  // `.nativeElement` would be undefined.
  private cardEls = viewChildren('cardEl', { read: ElementRef });

  constructor() {
    // Keep the focused card scrolled into view as focus moves.
    effect(() => {
      const index = this.focusedIndex();
      const el = this.cardEls()[index];
      el?.nativeElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  }

  ngOnInit(): void {
    this.load();
  }

  /** Fetch the list for the current view. */
  private load(): void {
    this.state.set('loading');
    const source = this.view() === 'queue' ? this.api.getQueue() : this.api.getHistory();
    source.subscribe({
      next: (papers) => {
        this.papers.set(papers);
        this.focusedIndex.set(0);
        this.state.set('ready');
      },
      error: () => this.state.set('error'),
    });
  }

  /** Switch between the pending queue and the decided-paper history. */
  setView(view: 'queue' | 'history'): void {
    if (view === this.view()) return;
    this.clearDecision();
    this.view.set(view);
    this.load();
  }

  ngOnDestroy(): void {
    if (this.undoTimer) clearTimeout(this.undoTimer);
  }

  toggleHelp(): void {
    this.showHelp.update((v) => !v);
  }

  decisionLabel(decision: Decision): string {
    return { kept: 'Kept', dismissed: 'Dismissed' }[decision] ?? decision;
  }

  /** Keyboard entry point: decide on the currently focused paper. */
  decide(decision: Decision): void {
    const paper = this.papers()[this.focusedIndex()];
    if (paper) this.decideOn(paper, decision);
  }

  /** Apply a decision to a specific paper (from a card button or keyboard). */
  decideOn(paper: Paper, decision: Decision): void {
    // History is read-only; decisions only apply to the pending queue.
    if (this.view() === 'history') return;
    const index = this.papers().findIndex((p) => p.id === paper.id);
    if (index < 0) return;

    const snapshot = this.papers();
    this.papers.update((list) => list.filter((p) => p.id !== paper.id));
    this.clampFocus();
    this.rememberDecision({ paper, index, decision });

    this.api.decide(paper.id, decision).subscribe({
      error: () => {
        // Roll back the optimistic removal if the write failed.
        this.papers.set(snapshot);
        this.focusedIndex.set(index);
        this.clearDecision();
        this.state.set('error');
      },
    });
  }

  openPaper(paper: Paper): void {
    window.open(paper.url, '_blank', 'noopener');
  }

  /** Undo the most recent decision, restoring the paper to its place. */
  undo(): void {
    const last = this.lastDecision();
    if (!last) return;
    this.api.undo(last.paper.id).subscribe({
      next: (restored) => {
        this.papers.update((list) => {
          const copy = [...list];
          copy.splice(Math.min(last.index, copy.length), 0, restored);
          return copy;
        });
        this.focusedIndex.set(Math.min(last.index, this.papers().length - 1));
        this.clearDecision();
      },
      // Window expired or already reverted server-side — just drop the hint.
      error: () => this.clearDecision(),
    });
  }

  private rememberDecision(decision: LastDecision): void {
    this.clearDecision();
    this.lastDecision.set(decision);
    this.undoTimer = setTimeout(() => this.lastDecision.set(null), UNDO_WINDOW_MS);
  }

  private clearDecision(): void {
    if (this.undoTimer) {
      clearTimeout(this.undoTimer);
      this.undoTimer = null;
    }
    this.lastDecision.set(null);
  }

  private clampFocus(): void {
    const count = this.papers().length;
    this.focusedIndex.set(count === 0 ? 0 : Math.min(this.focusedIndex(), count - 1));
  }

  @HostListener('window:keydown', ['$event'])
  handleKey(event: KeyboardEvent): void {
    // Don't hijack typing in form fields.
    const target = event.target as HTMLElement | null;
    if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;

    if (event.key === '?') {
      this.toggleHelp();
      event.preventDefault();
      return;
    }
    if (event.key === 'Escape') {
      this.showHelp.set(false);
      return;
    }
    if (this.showHelp()) return;

    switch (event.key) {
      case 'j':
      case 'ArrowDown':
        this.moveFocus(1);
        event.preventDefault();
        break;
      case 'k':
      case 'ArrowUp':
        this.moveFocus(-1);
        event.preventDefault();
        break;
      case 'o':
        this.openFocused();
        event.preventDefault();
        break;
      case 'd':
      case 'f':
        this.decide('kept');
        event.preventDefault();
        break;
      case 'x':
        this.decide('dismissed');
        event.preventDefault();
        break;
      case 'u':
        this.undo();
        event.preventDefault();
        break;
    }
  }

  private moveFocus(delta: number): void {
    const count = this.papers().length;
    if (count === 0) return;
    const next = Math.min(Math.max(this.focusedIndex() + delta, 0), count - 1);
    this.focusedIndex.set(next);
  }

  private openFocused(): void {
    const paper = this.papers()[this.focusedIndex()];
    if (paper) this.openPaper(paper);
  }
}
