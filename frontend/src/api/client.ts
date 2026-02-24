import axios from 'axios'
import type { Inspection, InspectionDetail, Violation, VoiceChatResponse } from '../types'

const api = axios.create({ baseURL: '/api' })

export const inspectionsApi = {
  list: () => api.get<Inspection[]>('/inspections').then(r => r.data),

  get: (id: string) => api.get<InspectionDetail>(`/inspections/${id}`).then(r => r.data),

  create: (formData: FormData) =>
    api.post<Inspection>('/inspections', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data),

  updateViolation: (
    inspectionId: string,
    violationId: string,
    patch: Partial<Pick<Violation, 'status' | 'assigned_to' | 'ticket_id' | 'ticket_url'>>
  ) =>
    api.patch<Violation>(`/inspections/${inspectionId}/violations/${violationId}`, patch)
      .then(r => r.data),

  delete: (id: string) => api.delete(`/inspections/${id}`),
}

export const voiceApi = {
  chat: (text: string, history?: object[]) =>
    api.post<VoiceChatResponse>('/voice/chat', { text, conversation_history: history ?? [] })
      .then(r => r.data),
}

export default api
