import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./pages/home/home.component').then(m => m.HomeComponent)
  },
  {
    path: 'publications',
    loadComponent: () => import('./pages/publications/publications.component').then(m => m.PublicationsComponent)
  },
  {
    path: 'blog',
    loadComponent: () => import('./pages/blog-list/blog-list.component').then(m => m.BlogListComponent)
  },
  {
    path: 'blog/:slug',
    loadComponent: () => import('./pages/blog-post/blog-post.component').then(m => m.BlogPostComponent)
  },
  {
    path: 'tapestry',
    loadComponent: () => import('./pages/tapestry/tapestry.component').then(m => m.TapestryComponent)
  },
  {
    // The overview stays mounted while a solution is open: the modal is a child
    // route rendered in its <router-outlet>, so its URL can be shared.
    path: 'puzzles',
    loadComponent: () => import('./pages/puzzles/puzzles.component').then(m => m.PuzzlesComponent),
    children: [
      { path: '', children: [] },
      {
        path: 'aoc/:year/:day',
        data: { kind: 'aoc' },
        loadComponent: () => import('./pages/puzzles/solution-modal.component').then(m => m.SolutionModalComponent)
      },
      {
        path: 'euler/:problem',
        data: { kind: 'euler' },
        loadComponent: () => import('./pages/puzzles/solution-modal.component').then(m => m.SolutionModalComponent)
      }
    ]
  },
  {
    path: 'privacy',
    loadComponent: () => import('./pages/privacy/privacy.component').then(m => m.PrivacyComponent)
  },
  {
    path: '**',
    redirectTo: ''
  }
];
