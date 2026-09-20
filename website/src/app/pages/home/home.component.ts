import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-home',
  standalone: true,
  template: `
    <div class="home">
      <h1>Welcome!</h1>
      <p>
        I'm a Data Scientist and System Developer based in Stockholm, Sweden, working at Uppsala Monitoring Centre.
        I'm currently stepping up as interim Science and Innovation lead, helping to coordinate and implement UMCs strategic mission. I'm also building agentic AI systems for signal assessment.
        This site is intended to be a playground for me to mess around with various web related things, and host some of my silly AI hobby projects (e.g., the Bayeux tapestry bot, linked above).
        I also use it to host an occasional blog, as and when I have some interesting stuff to write about.
      </p>
      <p>
        You can see all the source of this website — and the bots behind the hobby projects — on
        <a href="https://github.com/jimbarrett27/jimbarrett.dev" target="_blank" rel="noopener noreferrer">GitHub</a>.
      </p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [`
    .home {
      max-width: 720px;
      margin: 0 auto;
      padding: 2rem 1rem;
    }

    h1 {
      margin-bottom: 1.5rem;
    }

    p {
      margin-bottom: 1rem;
      line-height: 1.8;
    }

    a {
      color: #0f1219;
    }
  `]
})
export class HomeComponent {}
