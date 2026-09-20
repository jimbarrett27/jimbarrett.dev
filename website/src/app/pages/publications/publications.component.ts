import { Component, inject, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { PublicationsService } from '../../core/services/publications.service';
import { PublicationsData } from '../../core/models/publication.interface';

@Component({
  selector: 'app-publications',
  standalone: true,
  template: `
    <div class="publications">
      @if (publications()) {
        <section>
          <h2>First Author Publications</h2>
          @for (pub of publications()!.firstAuthor; track pub.url) {
            <div class="publication">
              <strong>{{ pub.title }}</strong><br>
              {{ pub.authors }}<br>
              <a [href]="pub.url" target="_blank" rel="noopener noreferrer">{{ pub.url }}</a>
            </div>
          }
        </section>

        <section>
          <h2>Other Publications</h2>
          @for (pub of publications()!.other; track pub.url) {
            <div class="publication">
              <strong>{{ pub.title }}</strong><br>
              {{ pub.authors }}<br>
              <a [href]="pub.url" target="_blank" rel="noopener noreferrer">{{ pub.url }}</a>
            </div>
          }
        </section>

        <section>
          <h2>Masters Theses Supervised</h2>
          @for (pub of publications()!.mastersTheses; track pub.url) {
            <div class="publication">
              <strong>{{ pub.title }}</strong><br>
              {{ pub.authors }}<br>
              <a [href]="pub.url" target="_blank" rel="noopener noreferrer">{{ pub.url }}</a>
            </div>
          }
        </section>

        <section>
          <h2>Patents</h2>
          @for (pub of publications()!.patents; track pub.url) {
            <div class="publication">
              <strong>{{ pub.title }}</strong><br>
              {{ pub.authors }}<br>
              <a [href]="pub.url" target="_blank" rel="noopener noreferrer">{{ pub.url }}</a>
            </div>
          }
        </section>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .publications {
      max-width: 720px;
      margin: 0 auto;
      padding: 2rem 1rem;
    }

    section {
      margin-bottom: 2rem;
    }

    h2 {
      margin-bottom: 1rem;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 0.5rem;
    }

    .publication {
      margin-bottom: 1.5rem;
      line-height: 1.6;
    }

    a {
      color: #0f1219;
      word-break: break-all;
    }
  `]
})
export class PublicationsComponent implements OnInit {
  private publicationsService = inject(PublicationsService);
  publications = signal<PublicationsData | null>(null);

  ngOnInit() {
    this.publicationsService.getPublications().subscribe(data => {
      this.publications.set(data);
    });
  }
}
