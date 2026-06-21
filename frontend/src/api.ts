import { Idea, IdeaDetail, IdeaExportRow, IdeaListParams, Sp500TotalReturnRow } from './types';

const API_BASE = '/api';

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export async function checkHealth() {
  return request<{ status: string }>('/health');
}

export async function getIdeas(params: IdeaListParams) {
  const search = new URLSearchParams({
    skip: String(params.skip),
    limit: String(params.limit),
    sort_by: 'date',
    sort_order: 'desc',
  });

  if (params.search) {
    search.set('search', params.search);
  }

  return request<Idea[]>(`/ideas/?${search.toString()}`);
}

export async function getIdeasCount(searchTerm?: string) {
  const search = new URLSearchParams();

  if (searchTerm) {
    search.set('search', searchTerm);
  }

  const suffix = search.toString() ? `?${search.toString()}` : '';
  return request<{ total: number }>(`/ideas/count${suffix}`);
}

export async function getIdea(id: string) {
  return request<IdeaDetail>(`/ideas/${encodeURIComponent(id)}`);
}

export async function getIdeasExport(searchTerm?: string) {
  const search = new URLSearchParams();

  if (searchTerm) {
    search.set('search', searchTerm);
  }

  const suffix = search.toString() ? `?${search.toString()}` : '';
  return request<IdeaExportRow[]>(`/ideas/export${suffix}`);
}

export async function getSp500TotalReturnExport() {
  return request<Sp500TotalReturnRow[]>('/benchmarks/sp500-total-return/export');
}
