import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Decision, Paper } from '../models/paper.model';

/**
 * Typed wrapper over the triage backend.
 *
 * The API is always same-origin: in dev `ng serve` forwards /api to the local
 * FastAPI server via proxy.conf.json, and in production Caddy serves this app
 * and proxies /api to the backend on triage.home.jimbarrett.dev.
 */
@Injectable({ providedIn: 'root' })
export class TriageApiService {
  private http = inject(HttpClient);
  private readonly base = '/api/triage';

  /** Pending papers awaiting a triage decision, best score first. */
  getQueue(): Observable<Paper[]> {
    return this.http.get<Paper[]>(`${this.base}/queue`);
  }

  /** Already-decided papers, newest decision first (history view). */
  getHistory(): Observable<Paper[]> {
    return this.http.get<Paper[]>(`${this.base}/history`);
  }

  // Writes send an empty body and pass data via query params, which is the
  // shape the backend's endpoints take.

  /** Record a triage decision for a paper. */
  decide(paperId: number, decision: Decision): Observable<Paper> {
    return this.http.post<Paper>(`${this.base}/papers/${paperId}/decide`, null, {
      params: { decision },
    });
  }

  /** Revert the most recent decision (only succeeds within the undo window). */
  undo(paperId: number): Observable<Paper> {
    return this.http.post<Paper>(`${this.base}/papers/${paperId}/undo`, null);
  }
}
