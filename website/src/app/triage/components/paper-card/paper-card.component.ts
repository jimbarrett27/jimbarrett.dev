import { Component, computed, input, output, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { Decision, Paper } from '../../models/paper.model';

type RoutingState = 'ok' | 'pending' | 'retrying' | 'failed';

interface RoutingBadge {
  target: string;
  state: RoutingState;
  detail: string;
}

/**
 * Presentational card for a single paper in the triage queue.
 *
 * Owns only its own local UI state (abstract expand/collapse). Focus and
 * keyboard handling live in the queue page, which drives the `focused` input.
 */
@Component({
  selector: 'app-paper-card',
  standalone: true,
  imports: [DatePipe],
  template: `
    <article class="card" [class.focused]="focused()">
      <header class="card-head">
        <h2 class="title">{{ paper().title }}</h2>
      </header>

      <p class="meta">
        <span class="authors">{{ authorsLabel() }}</span>
        <span class="sep">·</span>
        <span class="source">{{ paper().source_type }}</span>
        <span class="sep">·</span>
        <time>{{ paper().discovered_at | date: 'mediumDate' }}</time>
      </p>

      @if (paper().surfaced_by?.length) {
        <p class="signals">
          <span class="signals-label">surfaced by</span>
          @for (s of paper().surfaced_by; track s) {
            <span class="signal" [title]="signalHint(s)">{{ s }}</span>
          }
        </p>
      }

      @if (paper().abstract) {
        <p
          class="abstract"
          [class.clamped]="!expanded()"
          (click)="toggleAbstract()"
          [title]="expanded() ? 'Click to collapse' : 'Click to expand'"
        >
          {{ paper().abstract }}
        </p>
      }

      @if (paper().llm_reasoning) {
        <p class="reason"><strong>Why this surfaced:</strong> {{ paper().llm_reasoning }}</p>
      }

      @if (paper().llm_tags.length) {
        <p class="tags">
          @for (tag of paper().llm_tags; track tag) {
            <span class="tag">{{ tag }}</span>
          }
        </p>
      }

      @if (isDecided()) {
        <p class="routing">
          <span class="decided-as decided-{{ paper().status }}">{{ statusLabel() }}</span>
          @for (b of routingBadges(); track b.target) {
            <span class="rbadge rbadge-{{ b.state }}" [title]="b.detail">
              {{ b.target }} {{ stateIcon(b.state) }}
            </span>
          }
        </p>
      }

      <div class="actions">
        @if (!isDecided()) {
          <button
            class="act act-keep"
            (click)="$event.stopPropagation(); decide.emit('kept')"
            title="Keep — routes to Zotero + Obsidian (d / f)"
          >
            Keep
          </button>
          <button
            class="act act-dismiss"
            (click)="$event.stopPropagation(); decide.emit('dismissed')"
            title="Dismiss (x)"
          >
            Dismiss
          </button>
        }
        <button
          class="act act-open"
          (click)="$event.stopPropagation(); open.emit()"
          title="Open paper URL in a new tab (o)"
        >
          Open ↗
        </button>
      </div>
    </article>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [
    `
      .card {
        border: 1px solid var(--color-gray-light);
        border-radius: 8px;
        padding: 1rem 1.25rem;
        background: var(--color-white);
        transition:
          border-color 0.15s,
          box-shadow 0.15s;
        scroll-margin: 5rem;
      }

      .card.focused {
        border-color: var(--color-black);
        box-shadow: 0 0 0 2px var(--color-black);
        background: var(--color-gray-lighter);
      }

      .card-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 0.75rem;
      }

      .title {
        font-size: 1.15rem;
        line-height: 1.35;
        margin: 0;
      }

      .meta {
        color: var(--color-gray);
        font-size: 0.85rem;
        margin: 0.4rem 0 0.6rem;
      }
      .sep {
        margin: 0 0.4rem;
      }

      .signals {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.35rem;
        margin: 0 0 0.6rem;
      }
      .signals-label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--color-gray);
      }
      .signal {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        color: var(--color-black);
        background: var(--color-gray-lighter);
        border: 1px solid var(--color-gray-light);
        border-radius: 999px;
        padding: 0.05rem 0.5rem;
      }

      .abstract {
        margin: 0 0 0.6rem;
        cursor: pointer;
      }
      .abstract.clamped {
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

      .reason {
        margin: 0 0 0.6rem;
        font-size: 0.95rem;
      }

      .tags {
        margin: 0;
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
      }
      .tag {
        font-size: 0.75rem;
        color: var(--color-gray);
        background: var(--color-gray-lighter);
        border: 1px solid var(--color-gray-light);
        border-radius: 4px;
        padding: 0.05rem 0.4rem;
      }

      .routing {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.4rem;
        margin: 0.2rem 0 0;
        font-size: 0.8rem;
      }
      .decided-as {
        text-transform: uppercase;
        letter-spacing: 0.04em;
        font-size: 0.7rem;
        padding: 0.15rem 0.5rem;
        border-radius: 999px;
        border: 1px solid var(--color-gray-light);
        color: var(--color-gray);
      }
      .decided-kept {
        background: var(--color-black);
        color: var(--color-white);
        border-color: var(--color-black);
      }
      .decided-deep {
        background: var(--color-black);
        color: var(--color-white);
        border-color: var(--color-black);
      }
      .decided-dismissed {
        color: var(--color-gray);
      }
      .rbadge {
        font-size: 0.75rem;
        padding: 0.05rem 0.45rem;
        border-radius: 4px;
        border: 1px solid var(--color-gray-light);
        cursor: default;
      }
      .rbadge-ok {
        color: #15803d;
        border-color: #bbf7d0;
        background: #f0fdf4;
      }
      .rbadge-pending {
        color: var(--color-gray);
        background: var(--color-gray-lighter);
      }
      .rbadge-retrying {
        color: #b45309;
        border-color: #fde68a;
        background: #fffbeb;
      }
      .rbadge-failed {
        color: #b91c1c;
        border-color: #fecaca;
        background: #fef2f2;
      }

      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-top: 0.9rem;
        padding-top: 0.9rem;
        border-top: 1px solid var(--color-gray-light);
      }
      .act {
        font-family: var(--font-family);
        font-size: 0.85rem;
        cursor: pointer;
        padding: 0.3rem 0.75rem;
        border-radius: 6px;
        border: 1px solid var(--color-gray-light);
        background: var(--color-white);
        color: var(--color-black);
        transition:
          background 0.12s,
          border-color 0.12s;
      }
      .act:hover {
        background: var(--color-gray-lighter);
      }
      .act-keep {
        background: var(--color-black);
        color: var(--color-white);
        border-color: var(--color-black);
      }
      .act-keep:hover {
        opacity: 0.85;
        background: var(--color-black);
      }
      .act-dismiss {
        color: var(--color-gray);
      }
      .act-open {
        margin-left: auto;
      }
    `,
  ],
})
export class PaperCardComponent {
  paper = input.required<Paper>();
  focused = input<boolean>(false);

  decide = output<Decision>();
  open = output<void>();

  expanded = signal(false);

  authorsLabel = computed(() => {
    const authors = this.paper().authors;
    if (authors.length === 0) return 'Unknown authors';
    if (authors.length <= 3) return authors.join(', ');
    return `${authors.slice(0, 3).join(', ')} et al.`;
  });

  /** A paper is decided once it has left the `pending` state. */
  isDecided = computed(() => this.paper().status !== 'pending');

  statusLabel = computed(
    () =>
      ({
        kept: 'Kept',
        deep: 'Deep',
        filed: 'Filed',
        dismissed: 'Dismissed',
        auto_rejected: 'Auto-rejected',
        pending: 'Pending',
      })[this.paper().status],
  );

  /**
   * Per-target routing status, shown on decided cards. A target only appears
   * when the decision routes to it (`deep` → Zotero + Obsidian, `filed` →
   * Obsidian, `dismissed` → neither). State is derived from the success key,
   * the recorded error, and whether a retry is still scheduled.
   */
  routingBadges = computed<RoutingBadge[]>(() => {
    const p = this.paper();
    const badges: RoutingBadge[] = [];
    const add = (
      target: string,
      applies: boolean,
      success: string | null,
      error: string | null,
    ) => {
      if (!applies) return;
      if (success) {
        badges.push({ target, state: 'ok', detail: `${target}: ${success}` });
      } else if (error) {
        badges.push({
          target,
          state: p.next_retry_at ? 'retrying' : 'failed',
          detail: p.next_retry_at
            ? `${error} (retry scheduled; attempt ${p.routing_attempts})`
            : `${error} (gave up after ${p.routing_attempts} attempts)`,
        });
      } else {
        badges.push({ target, state: 'pending', detail: `${target} routing in progress…` });
      }
    };
    add('Zotero', p.status === 'kept' || p.status === 'deep', p.zotero_key, p.zotero_error);
    add(
      'Obsidian',
      p.status === 'kept' || p.status === 'deep' || p.status === 'filed',
      p.obsidian_path,
      p.obsidian_error,
    );
    return badges;
  });

  stateIcon(state: RoutingState): string {
    return { ok: '✓', pending: '…', retrying: '↻', failed: '✗' }[state];
  }

  toggleAbstract(): void {
    this.expanded.update((v) => !v);
  }

  signalHint(signal: string): string {
    switch (signal) {
      case 'keyword':
        return 'Matched a pharmacovigilance keyword';
      case 'topic':
        return 'Classified under a watched OpenAlex topic';
      case 'author':
        return 'Authored by a monitored author';
      case 'citation':
        return 'Cites a watched seed paper';
      case 'institution':
        return "Cites a watched institution's work";
      default:
        return '';
    }
  }

}
