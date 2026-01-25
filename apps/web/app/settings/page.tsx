'use client'

import { useState, useEffect } from 'react'
import { api, Settings as SettingsType } from '@/lib/api'
import { Loader2, ArrowLeft, CheckCircle } from 'lucide-react'
import Link from 'next/link'

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsType | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [formData, setFormData] = useState({
    modelName: '',
    apiKey: '',
  })

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      const data = await api.getSettings()
      setSettings(data)
      setFormData({
        modelName: data.model_name,
        apiKey: '',
      })
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaved(false)

    try {
      await api.updateSettings(
        formData.modelName || undefined,
        formData.apiKey || undefined
      )
      await loadSettings()
      setSaved(true)
      setFormData({ ...formData, apiKey: '' })
      setTimeout(() => setSaved(false), 3000)
    } catch (error) {
      console.error('Failed to save settings:', error)
      alert('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-2xl mx-auto p-6">
        {/* Header */}
        <div className="mb-8">
          <Link
            href="/chat"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Chat
          </Link>
          <h1 className="text-3xl font-bold">Settings</h1>
          <p className="text-muted-foreground mt-2">
            Configure your agent settings
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-12">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* API Key Status */}
            <div className="p-4 border border-border rounded-lg bg-muted/50">
              <div className="flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${
                    settings?.has_api_key ? 'bg-green-500' : 'bg-red-500'
                  }`}
                />
                <span className="text-sm font-medium">
                  API Key: {settings?.has_api_key ? 'Configured' : 'Not Set'}
                </span>
              </div>
              {!settings?.has_api_key && (
                <p className="text-xs text-muted-foreground mt-2">
                  Set your OpenAI API key in the server .env file or use the form below
                </p>
              )}
            </div>

            {/* Model Selection */}
            <div>
              <label className="block text-sm font-medium mb-2">
                Model Name
              </label>
              <input
                type="text"
                value={formData.modelName}
                onChange={(e) =>
                  setFormData({ ...formData, modelName: e.target.value })
                }
                placeholder="e.g., gpt-4o, gpt-4-turbo"
                className="w-full px-4 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Current: {settings?.model_name}
              </p>
            </div>

            {/* API Key */}
            <div>
              <label className="block text-sm font-medium mb-2">
                OpenAI API Key (Runtime Only)
              </label>
              <input
                type="password"
                value={formData.apiKey}
                onChange={(e) =>
                  setFormData({ ...formData, apiKey: e.target.value })
                }
                placeholder="sk-..."
                className="w-full px-4 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Note: This only updates the runtime setting, not the .env file. The key will be lost when the server restarts.
              </p>
            </div>

            {/* Info Box */}
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h3 className="text-sm font-semibold text-blue-900 mb-2">
                Environment Variables
              </h3>
              <p className="text-xs text-blue-800 mb-3">
                For persistent configuration, set these variables in your server .env file:
              </p>
              <ul className="text-xs text-blue-800 space-y-1 font-mono">
                <li>• OPENAI_API_KEY=your_key_here</li>
                <li>• MODEL_NAME=gpt-4o</li>
                <li>• PKM_ROOT=/path/to/vault</li>
                <li>• ALLOWED_FS_ROOT=/path/to/workspace</li>
              </ul>
            </div>

            {/* Save Button */}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={saving}
                className="px-6 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
              >
                {saving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                    Saving...
                  </>
                ) : (
                  'Save Settings'
                )}
              </button>
              {saved && (
                <div className="flex items-center gap-2 text-green-600">
                  <CheckCircle className="w-5 h-5" />
                  <span className="text-sm font-medium">Saved!</span>
                </div>
              )}
            </div>
          </form>
        )}

        {/* Additional Info */}
        <div className="mt-12 pt-8 border-t border-border">
          <h2 className="text-lg font-semibold mb-4">About Agent Blob</h2>
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>Version: 0.1.0</p>
            <p>Local-first AI agent with structured memory and tool execution</p>
            <p className="pt-4">
              <a
                href="https://github.com/yourusername/agent_blob"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                View on GitHub
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
