import { Component, ChangeDetectionStrategy } from '@angular/core';

/**
 * Privacy policy for the personal automations behind this site.
 *
 * Exists so the Google OAuth app the home server uses for Drive can be published
 * to production (Google requires a privacy policy URL for that). Not linked from
 * the header; it only needs to be reachable.
 */
@Component({
  selector: 'app-privacy',
  standalone: true,
  template: `
    <div class="privacy">
      <h2>Privacy policy</h2>

      <p>
        This site and the automations behind it are personal projects. They are run
        by me, for me, and have no other users.
      </p>

      <h3>Google account data</h3>
      <p>
        Some of these automations sign in to my own Google accounts. They use Google
        Drive only to store documents I want to read and to retrieve documents I have
        annotated, so that I can file my own notes.
      </p>
      <p>
        That data stays on my own server and in my own accounts. It is not sold,
        shared with anyone, or used for advertising. Its use complies with the
        <a href="https://developers.google.com/terms/api-services-user-data-policy"
           target="_blank" rel="noopener noreferrer">Google API Services User Data Policy</a>,
        including the Limited Use requirements.
      </p>

      <h3>Visitors to this site</h3>
      <p>
        This website does not use cookies, does not track you, and collects no
        personal information beyond the standard request logs kept by its hosting
        provider.
      </p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: [`
    .privacy {
      max-width: 720px;
      margin: 0 auto;
      padding: 2rem 1rem;
      line-height: 1.6;
    }

    h2 {
      margin-bottom: 1rem;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 0.5rem;
    }

    h3 {
      margin-top: 1.5rem;
    }

    a {
      color: #0f1219;
    }
  `]
})
export class PrivacyComponent {}
