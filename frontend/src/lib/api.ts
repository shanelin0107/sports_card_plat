const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export async function fetchDashboardSummary() {
  const res = await fetch(`${API_BASE}/api/v1/dashboard/summary`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to load dashboard summary');
  return res.json();
}

export async function fetchDashboardDistribution(by: 'brand' | 'player' | 'grade' = 'brand') {
  const res = await fetch(`${API_BASE}/api/v1/dashboard/distribution?by=${by}`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to load distribution');
  return res.json();
}

export async function fetchRecentAdditions() {
  const res = await fetch(`${API_BASE}/api/v1/dashboard/recent-additions`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to load recent additions');
  return res.json();
}

export async function searchCards(query: string) {
  const res = await fetch(`${API_BASE}/api/v1/cards/search?q=${encodeURIComponent(query)}`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Failed to search cards');
  return res.json();
}

export async function fetchCardDetail(cardId: string) {
  const res = await fetch(`${API_BASE}/api/v1/cards/${cardId}`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch card detail');
  return res.json();
}

export async function fetchCardComps(cardId: string) {
  const res = await fetch(`${API_BASE}/api/v1/cards/${cardId}/comps?window=90d&limit=10`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch comps');
  return res.json();
}

export async function fetchCardHistory(cardId: string, window = '90d') {
  const res = await fetch(`${API_BASE}/api/v1/cards/${cardId}/sales-history?window=${window}&bucket=day`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Failed to fetch sales history');
  return res.json();
}

export async function fetchCollectionItems() {
  const res = await fetch(`${API_BASE}/api/v1/collection/items`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch collection');
  return res.json();
}

export async function addCollectionItem(payload: any) {
  const res = await fetch(`${API_BASE}/api/v1/collection/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to add collection item');
  return res.json();
}

export async function updateCollectionItem(itemId: number, payload: any) {
  const res = await fetch(`${API_BASE}/api/v1/collection/items/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to update collection item');
  return res.json();
}

export async function deleteCollectionItem(itemId: number) {
  const res = await fetch(`${API_BASE}/api/v1/collection/items/${itemId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete collection item');
  return res.json();
}
