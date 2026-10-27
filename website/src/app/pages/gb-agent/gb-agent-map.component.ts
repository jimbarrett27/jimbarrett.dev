import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { GbAgentMap, GbAgentPos } from '../../core/models/gb-agent.interface';
import { tileRuns } from './gb-agent.format';

/** The whole map the player is on, one rect per run of tiles, with the player as a dot. */
@Component({
  selector: 'app-gb-agent-map',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg [attr.viewBox]="'0 0 ' + map().width + ' ' + map().height"
         shape-rendering="crispEdges" role="img" [attr.aria-label]="'Map of ' + (map().name ?? 'here')">
      @for (t of tiles(); track $index) {
        <rect [attr.x]="t.x" [attr.y]="t.y" [attr.width]="t.width" height="1" [attr.class]="'t-' + t.kind" />
      }
      @for (e of map().exits ?? []; track $index) {
        <rect [attr.x]="e.x" [attr.y]="e.y" width="1" height="1" class="t-exit"><title>{{ e.to }}</title></rect>
      }
      @if (dot(); as d) {
        <circle [attr.cx]="d.x" [attr.cy]="d.y" r=".6" class="t-player" />
      }
    </svg>
    <p class="legend">
      @for (k of legend; track k) { <span class="key t-{{ k }}"></span>{{ k }} }
    </p>
  `,
  styles: [`
    svg { display: block; width: 100%; max-height: 320px; background: var(--color-black); border-radius: 4px; }
    .legend { display: flex; flex-wrap: wrap; align-items: center; gap: .25rem .4rem; margin: .75rem 0 0;
      font-size: .8rem; color: var(--color-gray); }
    .key { display: inline-block; width: .7rem; height: .7rem; border-radius: 2px; margin-left: .4rem; }
    .t-floor { fill: #e7e2cf; background: #e7e2cf; }
    .t-wall { fill: #6b7280; background: #6b7280; }
    .t-water { fill: #60a5fa; background: #60a5fa; }
    .t-grass { fill: #4ade80; background: #4ade80; }
    .t-ledge { fill: #a16207; background: #a16207; }
    .t-off { fill: var(--color-black); }
    .t-exit { fill: #f59e0b; background: #f59e0b; }
    .t-player { fill: #dc2626; background: #dc2626; stroke: var(--color-white); stroke-width: .15; border-radius: 50%; }
  `],
})
export class GbAgentMapComponent {
  readonly map = input.required<GbAgentMap>();
  readonly pos = input<GbAgentPos | null>(null);
  readonly tiles = computed(() => tileRuns(this.map().rows ?? []));
  /** The player's tile centre, kept on the map: crossing an edge, the game puts the
   *  player a tile outside it until the next map loads. */
  readonly dot = computed(() => {
    const p = this.pos(), m = this.map();
    if (p?.x == null || p?.y == null) return null;
    const clamp = (v: number, size: number) => Math.max(0, Math.min(size - 1, v)) + 0.5;
    return { x: clamp(p.x, m.width), y: clamp(p.y, m.height) };
  });
  readonly legend = ['floor', 'grass', 'water', 'ledge', 'exit', 'player'];
}
