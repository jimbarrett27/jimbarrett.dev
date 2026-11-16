import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  template: `
    <header>
      <nav>
        <a routerLink="/" class="site-title">Jim W. Barrett</a>
        <div class="nav-links">
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact: true}">Home</a>
          <a routerLink="/publications" routerLinkActive="active">Publications</a>
          <a routerLink="/blog" routerLinkActive="active">Blog</a>
          <a routerLink="/tapestry" routerLinkActive="active">Tapestry</a>
        </div>
      </nav>
    </header>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    header {
      background: #fff;
      border-bottom: 1px solid #e5e7eb;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    nav {
      max-width: 960px;
      margin: 0 auto;
      padding: 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }

    .site-title {
      font-size: 1.25rem;
      font-weight: bold;
      text-decoration: none;
      color: #0f1219;
    }

    .nav-links {
      display: flex;
      gap: 1.5rem;
    }

    .nav-links a {
      text-decoration: none;
      color: #6b7280;
      transition: color 0.2s;
    }

    .nav-links a:hover,
    .nav-links a.active {
      color: #0f1219;
    }

    @media (max-width: 480px) {
      nav {
        flex-direction: column;
        align-items: flex-start;
      }

      .nav-links {
        gap: 1rem;
      }
    }
  `]
})
export class HeaderComponent {}
