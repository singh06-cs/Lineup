// One function per backend endpoint, so components never build URLs themselves.
import { request, tokens } from './client'

export const auth = {
  async login(username, password) {
    const data = await request('/api/auth/login/', {
      method: 'POST', body: { username, password }, auth: false,
    })
    tokens.save(data)
  },
  register: (fields) => request('/api/auth/register/', { method: 'POST', body: fields, auth: false }),
  async logout() {
    try {
      await request('/api/auth/logout/', { method: 'POST', body: { refresh: tokens.refresh } })
    } finally {
      tokens.clear()
    }
  },
  me: () => request('/api/auth/me/'),
}

export const organizations = {
  list: () => request('/api/organizations/'),
  get: (id) => request(`/api/organizations/${id}/`),
  create: (fields) => request('/api/organizations/', { method: 'POST', body: fields }),
  update: (id, fields) => request(`/api/organizations/${id}/`, { method: 'PATCH', body: fields }),
  remove: (id) => request(`/api/organizations/${id}/`, { method: 'DELETE' }),
  join: (inviteCode) => request('/api/organizations/join/', {
    method: 'POST', body: { invite_code: inviteCode },
  }),
  leave: (id) => request(`/api/organizations/${id}/leave/`, { method: 'POST' }),
  regenerateInviteCode: (id) => request(`/api/organizations/${id}/regenerate-invite-code/`, {
    method: 'POST',
  }),
  members: (id) => request(`/api/organizations/${id}/members/`),
  setRole: (id, membershipId, role) => request(`/api/organizations/${id}/members/${membershipId}/`, {
    method: 'PATCH', body: { role },
  }),
  removeMember: (id, membershipId) => request(`/api/organizations/${id}/members/${membershipId}/`, {
    method: 'DELETE',
  }),
}

export const shifts = {
  // params become the query string, e.g. {upcoming: true, organization: 3}
  list(params = {}) {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== '' && value !== undefined),
    )
    return request(`/api/shifts/?${query}`)
  },
  nextPage: (url) => request(url),
  create: (fields) => request('/api/shifts/', { method: 'POST', body: fields }),
  update: (id, fields) => request(`/api/shifts/${id}/`, { method: 'PATCH', body: fields }),
  remove: (id) => request(`/api/shifts/${id}/`, { method: 'DELETE' }),
  signUp: (id) => request(`/api/shifts/${id}/signup/`, { method: 'POST' }),
  cancel: (id) => request(`/api/shifts/${id}/signup/`, { method: 'DELETE' }),
  roster: (id) => request(`/api/shifts/${id}/roster/`),
}
