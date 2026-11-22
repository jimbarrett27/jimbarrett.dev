import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * A row of gold stars, drawn as SVG rather than the ★ character: Comic Shanns has
 * no star glyph, so the character fell back to whatever font the device had, or
 * to an empty box where it had none. Sized in em, so it follows the text around it.
 */
@Component({
  selector: 'app-stars',
  standalone: true,
  template: `
    @for (i of indices(); track i) {
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z" />
      </svg>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  host: { class: 'stars', '[attr.aria-label]': 'label()', role: 'img' },
  styles: [`
    :host { display: inline-flex; gap: 0.05em; color: var(--color-gold); vertical-align: -0.1em; }
    svg { width: 0.9em; height: 0.9em; fill: currentColor; }
  `],
})
export class StarsComponent {
  readonly count = input(1);
  readonly indices = computed(() => Array.from({ length: Math.max(0, this.count()) }, (_, i) => i));
  readonly label = computed(() => `${this.count()} ${this.count() === 1 ? 'star' : 'stars'}`);
}
