import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DatePipe } from '@angular/common';
import { GbAgentOracleEntry } from '../../core/models/gb-agent.interface';

/** The oracle's newest commentary, with the earlier ones folded away. */
@Component({
  selector: 'app-gb-agent-oracle',
  standalone: true,
  imports: [DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (latest(); as e) {
      <section class="oracle" aria-label="The oracle's commentary">
        <h2>ORACLE <span>· {{ e.time | date:'EEE d MMM, HH:mm' }}{{ e.model ? ' · ' + model(e.model) : '' }}</span></h2>
        @for (p of paragraphs(e); track $index) { <p>{{ p }}</p> }
        @if (earlier().length) {
          <details>
            <summary>earlier commentary</summary>
            @for (old of earlier(); track old.time) {
              <article>
                <h3>{{ old.time | date:'EEE d MMM, HH:mm' }}</h3>
                @for (p of paragraphs(old); track $index) { <p>{{ p }}</p> }
              </article>
            }
          </details>
        }
      </section>
    }
  `,
  styles: [`
    .oracle { border-left: 4px solid #6d28d9; background: var(--color-gray-lighter); border-radius: 0 8px 8px 0;
      padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: .6rem; }
    h2 { font-size: .875rem; font-weight: 400; letter-spacing: .05em; color: var(--color-gray); }
    h2 span { color: var(--color-gray); }
    p { margin: 0; max-width: 75ch; }
    summary { cursor: pointer; font-size: .8rem; color: var(--color-gray); }
    article { margin-top: .9rem; display: flex; flex-direction: column; gap: .4rem; font-size: .9rem; }
    h3 { font-size: .8rem; font-weight: 400; color: var(--color-gray); }
  `],
})
export class GbAgentOracleComponent {
  /** Oldest first, as in `oracle.json`. */
  readonly entries = input<GbAgentOracleEntry[]>([]);
  readonly latest = computed(() => this.entries().at(-1) ?? null);
  readonly earlier = computed(() => this.entries().slice(0, -1).reverse());

  paragraphs(e: GbAgentOracleEntry): string[] {
    return (e.text ?? '').split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
  }

  /** "deepseek-v4-pro" from "deepseek/deepseek-v4-pro". */
  model(id: string): string {
    return id.split('/').pop() ?? id;
  }
}
