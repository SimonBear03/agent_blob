/**
 * API client for Agent Blob backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

// Types
export interface Thread {
  id: string
  title: string | null
  created_at: string
  updated_at: string
  metadata: string | null
}

export interface Message {
  id: string
  thread_id: string
  role: string
  content: string
  created_at: string
  tool_calls?: string | null
  tool_call_id?: string | null
  name?: string | null
}

export interface Memory {
  id: string
  key: string
  value: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface ChatResponse {
  thread_id: string
  message: Message
  assistant_message: Message
}

export interface Settings {
  model_name: string
  has_api_key: boolean
}

// API functions
export const api = {
  // Threads
  async listThreads(): Promise<Thread[]> {
    const res = await fetch(`${API_URL}/threads`)
    if (!res.ok) throw new Error('Failed to list threads')
    return res.json()
  },

  async createThread(title?: string): Promise<Thread> {
    const res = await fetch(`${API_URL}/threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (!res.ok) throw new Error('Failed to create thread')
    return res.json()
  },

  async getThread(threadId: string): Promise<Thread> {
    const res = await fetch(`${API_URL}/threads/${threadId}`)
    if (!res.ok) throw new Error('Failed to get thread')
    return res.json()
  },

  async deleteThread(threadId: string): Promise<void> {
    const res = await fetch(`${API_URL}/threads/${threadId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete thread')
  },

  // Messages
  async listMessages(threadId: string): Promise<Message[]> {
    const res = await fetch(`${API_URL}/threads/${threadId}/messages`)
    if (!res.ok) throw new Error('Failed to list messages')
    return res.json()
  },

  // Chat
  async sendMessage(message: string, threadId?: string): Promise<ChatResponse> {
    const res = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, thread_id: threadId }),
    })
    if (!res.ok) {
      const error = await res.json()
      throw new Error(error.detail || 'Failed to send message')
    }
    return res.json()
  },

  // Memory
  async listMemories(): Promise<Memory[]> {
    const res = await fetch(`${API_URL}/pinned-memory`)
    if (!res.ok) throw new Error('Failed to list memories')
    return res.json()
  },

  async getMemory(key: string): Promise<Memory> {
    const res = await fetch(`${API_URL}/pinned-memory/${key}`)
    if (!res.ok) throw new Error('Failed to get memory')
    return res.json()
  },

  async setMemory(key: string, value: string, description?: string): Promise<Memory> {
    const res = await fetch(`${API_URL}/pinned-memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value, description }),
    })
    if (!res.ok) throw new Error('Failed to set memory')
    return res.json()
  },

  async deleteMemory(key: string): Promise<void> {
    const res = await fetch(`${API_URL}/pinned-memory/${key}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete memory')
  },

  // Settings
  async getSettings(): Promise<Settings> {
    const res = await fetch(`${API_URL}/settings`)
    if (!res.ok) throw new Error('Failed to get settings')
    return res.json()
  },

  async updateSettings(modelName?: string, apiKey?: string): Promise<void> {
    const res = await fetch(`${API_URL}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model_name: modelName,
        openai_api_key: apiKey,
      }),
    })
    if (!res.ok) throw new Error('Failed to update settings')
  },
}
