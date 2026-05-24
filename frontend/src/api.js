const JSON_HEADERS = {
  'Content-Type': 'application/json',
};

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || JSON.stringify(payload);
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }
  return response.json();
}

export function getBatches() {
  return request('/api/batches/');
}

export function getActivities(query = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, value);
    }
  });
  const suffix = params.toString() ? `?${params}` : '';
  return request(`/api/activities/${suffix}`);
}

export function getActivity(id) {
  return request(`/api/activities/${id}/`);
}

export function patchActivity(id, payload) {
  return request(`/api/activities/${id}/`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
}

export function reviewActivity(id, action, reason = '') {
  return request(`/api/activities/${id}/${action}/`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ reason }),
  });
}
