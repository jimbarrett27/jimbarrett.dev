import { Component, output, ChangeDetectionStrategy } from '@angular/core';
import { SHORTCUTS } from '../../shortcuts';

/** Modal overlay listing keyboard shortcuts, toggled with `?`. */
@Component({
  selector: 'app-shortcut-help',
  standalone: true,
  template: `
    <div class="backdrop" (click)="close.emit()">
      <div class="panel" role="dialog" aria-label="Keyboard shortcuts" (click)="$event.stopPropagation()">
        <h2>Keyboard shortcuts</h2>
        <dl>
          @for (s of shortcuts; track s.description) {
            <div class="row">
              <dt>
                @for (k of s.keys; track k) {
                  <kbd>{{ k }}</kbd>
                }
              </dt>
              <dd>{{ s.description }}</dd>
            </div>
          }
        </dl>
        <button class="dismiss" (click)="close.emit()">Close (Esc)</button>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [
    `
      .backdrop {
        position: fixed;
        inset: 0;
        background: rgba(15, 18, 25, 0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
      }
      .panel {
        background: var(--color-white);
        border: 1px solid var(--color-gray-light);
        border-radius: 8px;
        padding: 1.5rem 1.75rem;
        max-width: 420px;
        width: calc(100% - 2rem);
      }
      h2 {
        margin: 0 0 1rem;
        font-size: 1.25rem;
      }
      dl {
        margin: 0 0 1.25rem;
      }
      .row {
        display: flex;
        align-items: baseline;
        gap: 1rem;
        padding: 0.3rem 0;
      }
      dt {
        flex: 0 0 5.5rem;
        display: flex;
        gap: 0.3rem;
      }
      dd {
        margin: 0;
        color: var(--color-gray);
      }
      kbd {
        font-family: var(--font-family);
        font-size: 0.8rem;
        border: 1px solid var(--color-gray-light);
        border-bottom-width: 2px;
        border-radius: 4px;
        padding: 0.1rem 0.4rem;
        background: var(--color-gray-lighter);
      }
      .dismiss {
        font-family: var(--font-family);
        cursor: pointer;
        border: 1px solid var(--color-gray-light);
        background: var(--color-white);
        border-radius: 4px;
        padding: 0.4rem 0.8rem;
      }
      .dismiss:hover {
        background: var(--color-gray-lighter);
      }
    `,
  ],
})
export class ShortcutHelpComponent {
  close = output<void>();
  readonly shortcuts = SHORTCUTS;
}
