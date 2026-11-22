import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, shareReplay } from 'rxjs';
import { AocSolution, EulerSolution, PuzzlesIndex } from '../models/puzzles.interface';

const pad = (n: number, width: number) => String(n).padStart(width, '0');

@Injectable({ providedIn: 'root' })
export class PuzzlesService {
  private http = inject(HttpClient);

  /** Shared between the overview and the modal, so it's only fetched once. */
  private readonly index$ = this.http
    .get<PuzzlesIndex>('/assets/puzzles/index.json')
    .pipe(shareReplay({ bufferSize: 1, refCount: false }));

  getIndex(): Observable<PuzzlesIndex> {
    return this.index$;
  }

  getAocSolution(year: number, day: number): Observable<AocSolution> {
    return this.http.get<AocSolution>(`/assets/puzzles/aoc/${year}/${pad(day, 2)}.json`);
  }

  getEulerSolution(problem: number): Observable<EulerSolution> {
    return this.http.get<EulerSolution>(`/assets/puzzles/euler/${pad(problem, 3)}.json`);
  }
}
