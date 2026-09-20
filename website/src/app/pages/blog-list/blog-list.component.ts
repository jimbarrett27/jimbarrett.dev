import { Component, inject, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { BlogService } from '../../core/services/blog.service';
import { BlogPostSummary } from '../../core/models/blog-post.interface';

@Component({
  selector: 'app-blog-list',
  standalone: true,
  imports: [RouterLink, DatePipe],
  template: `
    <div class="blog-list">
      <h1>Blog</h1>
      <div class="posts-grid">
        @for (post of posts(); track post.slug) {
          <a [routerLink]="['/blog', post.slug]" class="post-card">
            @if (post.heroImage) {
              <img [src]="getImagePath(post.heroImage)" [alt]="post.title" class="hero-image">
            }
            <div class="post-info">
              <h2>{{ post.title }}</h2>
              @if (post.pubDate) {
                <time>{{ post.pubDate | date:'mediumDate' }}</time>
              }
              @if (post.description) {
                <p>{{ post.description }}</p>
              }
            </div>
          </a>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .blog-list {
      max-width: 960px;
      margin: 0 auto;
      padding: 2rem 1rem;
    }

    h1 {
      margin-bottom: 2rem;
    }

    .posts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 2rem;
    }

    .post-card {
      display: block;
      text-decoration: none;
      color: inherit;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      overflow: hidden;
      transition: box-shadow 0.2s;
    }

    .post-card:hover {
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .hero-image {
      width: 100%;
      height: 180px;
      object-fit: cover;
    }

    .post-info {
      padding: 1rem;
    }

    .post-info h2 {
      font-size: 1.25rem;
      margin-bottom: 0.5rem;
    }

    .post-info time {
      color: #6b7280;
      font-size: 0.875rem;
    }

    .post-info p {
      margin-top: 0.5rem;
      color: #6b7280;
      font-size: 0.875rem;
    }
  `]
})
export class BlogListComponent implements OnInit {
  private blogService = inject(BlogService);
  posts = signal<BlogPostSummary[]>([]);

  ngOnInit() {
    this.blogService.getBlogList().subscribe(posts => {
      this.posts.set(posts);
    });
  }

  getImagePath(heroImage: string): string {
    if (heroImage.startsWith('/')) {
      return '/assets/images' + heroImage;
    }
    return heroImage;
  }
}
