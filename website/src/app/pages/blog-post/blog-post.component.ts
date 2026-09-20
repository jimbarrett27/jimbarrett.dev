import { Component, inject, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { DatePipe } from '@angular/common';
import { BlogService } from '../../core/services/blog.service';
import { BlogPost } from '../../core/models/blog-post.interface';
import { SafeHtmlPipe } from '../../shared/pipes/safe-html.pipe';

declare global {
  interface Window {
    MathJax?: {
      typeset: (elements?: HTMLElement[]) => void;
      typesetPromise?: (elements?: HTMLElement[]) => Promise<void>;
      startup?: {
        promise: Promise<void>;
      };
    };
  }
}

@Component({
  selector: 'app-blog-post',
  standalone: true,
  imports: [DatePipe, SafeHtmlPipe],
  template: `
    <article class="blog-post">
      @if (post()) {
        @if (post()!.heroImage) {
          <img [src]="getImagePath(post()!.heroImage!)" [alt]="post()!.title" class="hero-image">
        }
        <header>
          <h1>{{ post()!.title }}</h1>
          <div class="meta">
            @if (post()!.pubDate) {
              <time>Published: {{ post()!.pubDate | date:'mediumDate' }}</time>
            }
            @if (post()!.updatedDate) {
              <time>Updated: {{ post()!.updatedDate | date:'mediumDate' }}</time>
            }
          </div>
        </header>
        <div class="content" [innerHTML]="post()!.content | safeHtml"></div>
      }
    </article>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .blog-post {
      max-width: 720px;
      margin: 0 auto;
      padding: 2rem 1rem;
    }

    .hero-image {
      width: 100%;
      max-height: 400px;
      object-fit: cover;
      border-radius: 8px;
      margin-bottom: 2rem;
    }

    header {
      margin-bottom: 2rem;
    }

    h1 {
      margin-bottom: 0.5rem;
    }

    .meta {
      color: #6b7280;
      font-size: 0.875rem;
    }

    .meta time {
      margin-right: 1rem;
    }

    .content {
      line-height: 1.8;
    }

    .content :deep(h2) {
      margin-top: 2rem;
      margin-bottom: 1rem;
    }

    .content :deep(p) {
      margin-bottom: 1rem;
    }

    .content :deep(a) {
      color: #0f1219;
    }

    .content :deep(pre) {
      background: #f3f4f6;
      padding: 1rem;
      border-radius: 4px;
      overflow-x: auto;
      margin-bottom: 1rem;
    }

    .content :deep(code) {
      font-family: 'Comic Shanns Mono', monospace;
      font-size: 0.9em;
    }

    .content :deep(img) {
      max-width: 100%;
      height: auto;
      border-radius: 4px;
    }

    .content :deep(iframe) {
      width: 100%;
      border: none;
      margin: 1rem 0;
    }

    .content :deep(blockquote) {
      border-left: 4px solid #e5e7eb;
      padding-left: 1rem;
      margin: 1rem 0;
      color: #6b7280;
    }
  `]
})
export class BlogPostComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private blogService = inject(BlogService);

  post = signal<BlogPost | null>(null);

  ngOnInit() {
    const slug = this.route.snapshot.paramMap.get('slug');
    if (slug) {
      this.blogService.getBlogPost(slug).subscribe(post => {
        this.post.set(post);
        // Wait for DOM update then trigger MathJax
        setTimeout(() => this.renderMathJax(), 100);
      });
    }
  }

  private renderMathJax() {
    if (window.MathJax) {
      if (window.MathJax.typesetPromise) {
        window.MathJax.typesetPromise().catch((err: Error) =>
          console.warn('MathJax typeset failed:', err)
        );
      } else if (window.MathJax.typeset) {
        window.MathJax.typeset();
      }
    }
  }

  getImagePath(heroImage: string): string {
    if (heroImage.startsWith('/')) {
      return '/assets/images' + heroImage;
    }
    return heroImage;
  }
}
