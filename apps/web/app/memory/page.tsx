'use client'

import { useState, useEffect } from 'react'
import { api, Memory } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { Loader2, Plus, Trash2, ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({
    key: '',
    value: '',
    description: '',
  })

  useEffect(() => {
    loadMemories()
  }, [])

  const loadMemories = async () => {
    try {
      const data = await api.listMemories()
      setMemories(data)
    } catch (error) {
      console.error('Failed to load memories:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.key.trim() || !formData.value.trim()) return

    try {
      await api.setMemory(formData.key, formData.value, formData.description || undefined)
      await loadMemories()
      setFormData({ key: '', value: '', description: '' })
      setEditing(false)
    } catch (error) {
      console.error('Failed to save memory:', error)
      alert('Failed to save memory')
    }
  }

  const handleDelete = async (key: string) => {
    if (!confirm(`Delete memory "${key}"?`)) return

    try {
      await api.deleteMemory(key)
      await loadMemories()
    } catch (error) {
      console.error('Failed to delete memory:', error)
      alert('Failed to delete memory')
    }
  }

  const handleEdit = (memory: Memory) => {
    setFormData({
      key: memory.key,
      value: memory.value,
      description: memory.description || '',
    })
    setEditing(true)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto p-6">
        {/* Header */}
        <div className="mb-8">
          <Link
            href="/chat"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Chat
          </Link>
          <h1 className="text-3xl font-bold">Pinned Memory</h1>
          <p className="text-muted-foreground mt-2">
            Persistent context that spans across conversations
          </p>
        </div>

        {/* Add/Edit Form */}
        <div className="mb-8 p-6 border border-border rounded-lg">
          <h2 className="text-xl font-semibold mb-4">
            {editing ? 'Edit Memory' : 'Add New Memory'}
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Key <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.key}
                onChange={(e) => setFormData({ ...formData, key: e.target.value })}
                placeholder="e.g., user_timezone, project_name"
                className="w-full px-4 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">
                Value <span className="text-red-500">*</span>
              </label>
              <textarea
                value={formData.value}
                onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                placeholder="The memory content"
                rows={3}
                className="w-full px-4 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">
                Description (optional)
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="What this memory represents"
                className="w-full px-4 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="flex gap-3">
              <button
                type="submit"
                className="px-6 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
              >
                {editing ? 'Update' : 'Add'} Memory
              </button>
              {editing && (
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false)
                    setFormData({ key: '', value: '', description: '' })
                  }}
                  className="px-6 py-2 border border-border rounded-md hover:bg-accent"
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Memories List */}
        <div>
          <h2 className="text-xl font-semibold mb-4">Stored Memories</h2>
          {loading ? (
            <div className="flex items-center justify-center p-12">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
          ) : memories.length === 0 ? (
            <div className="text-center p-12 border border-border border-dashed rounded-lg">
              <p className="text-muted-foreground">No memories stored yet</p>
            </div>
          ) : (
            <div className="space-y-4">
              {memories.map((memory) => (
                <div
                  key={memory.id}
                  className="p-6 border border-border rounded-lg hover:border-ring transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <code className="text-lg font-mono font-semibold">
                          {memory.key}
                        </code>
                        <span className="text-xs text-muted-foreground">
                          Updated {formatDate(memory.updated_at)}
                        </span>
                      </div>
                      {memory.description && (
                        <p className="text-sm text-muted-foreground mb-3">
                          {memory.description}
                        </p>
                      )}
                      <div className="bg-muted rounded-md p-3">
                        <pre className="text-sm whitespace-pre-wrap">
                          {memory.value}
                        </pre>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleEdit(memory)}
                        className="px-3 py-2 text-sm border border-border rounded-md hover:bg-accent"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(memory.key)}
                        className="px-3 py-2 text-sm border border-red-300 text-red-600 rounded-md hover:bg-red-50"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
