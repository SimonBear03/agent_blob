'use client'

import { useState, useEffect, useRef } from 'react'
import { api, Thread, Message } from '@/lib/api'
import { cn, formatDate } from '@/lib/utils'
import { MessageSquare, Plus, Send, Loader2, Trash2 } from 'lucide-react'
import Link from 'next/link'

export default function ChatPage() {
  const [threads, setThreads] = useState<Thread[]>([])
  const [currentThread, setCurrentThread] = useState<Thread | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingThreads, setLoadingThreads] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadThreads()
  }, [])

  useEffect(() => {
    if (currentThread) {
      loadMessages(currentThread.id)
    }
  }, [currentThread])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadThreads = async () => {
    try {
      const data = await api.listThreads()
      setThreads(data)
      if (data.length > 0 && !currentThread) {
        setCurrentThread(data[0])
      }
    } catch (error) {
      console.error('Failed to load threads:', error)
    } finally {
      setLoadingThreads(false)
    }
  }

  const loadMessages = async (threadId: string) => {
    try {
      const data = await api.listMessages(threadId)
      setMessages(data)
    } catch (error) {
      console.error('Failed to load messages:', error)
    }
  }

  const createNewThread = async () => {
    try {
      const thread = await api.createThread('New conversation')
      setThreads([thread, ...threads])
      setCurrentThread(thread)
      setMessages([])
    } catch (error) {
      console.error('Failed to create thread:', error)
    }
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const userMessage = input
    setInput('')
    setLoading(true)

    try {
      const response = await api.sendMessage(
        userMessage,
        currentThread?.id
      )

      // If new thread was created
      if (!currentThread || response.thread_id !== currentThread.id) {
        const thread = await api.getThread(response.thread_id)
        setCurrentThread(thread)
        setThreads([thread, ...threads.filter(t => t.id !== thread.id)])
      }

      // Reload messages
      await loadMessages(response.thread_id)
    } catch (error) {
      console.error('Failed to send message:', error)
      alert('Failed to send message: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const deleteThread = async (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation() // Prevent selecting the thread when clicking delete
    
    if (!confirm('Delete this conversation?')) return

    try {
      await api.deleteThread(threadId)
      
      // Remove from list
      setThreads(threads.filter(t => t.id !== threadId))
      
      // If we deleted the current thread, select another one
      if (currentThread?.id === threadId) {
        const remaining = threads.filter(t => t.id !== threadId)
        setCurrentThread(remaining.length > 0 ? remaining[0] : null)
        setMessages([])
      }
    } catch (error) {
      console.error('Failed to delete thread:', error)
      alert('Failed to delete conversation')
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="w-64 border-r border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <h1 className="text-xl font-bold">Agent Blob</h1>
        </div>

        <div className="p-4">
          <button
            onClick={createNewThread}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loadingThreads ? (
            <div className="flex items-center justify-center p-4">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : threads.length === 0 ? (
            <div className="p-4 text-sm text-muted-foreground text-center">
              No conversations yet
            </div>
          ) : (
            threads.map((thread) => (
              <div
                key={thread.id}
                className={cn(
                  'group relative w-full text-left px-4 py-3 hover:bg-accent transition-colors cursor-pointer',
                  currentThread?.id === thread.id && 'bg-accent'
                )}
                onClick={() => setCurrentThread(thread)}
              >
                <div className="flex items-start gap-2">
                  <MessageSquare className="w-4 h-4 mt-1 flex-shrink-0" />
                  <div className="flex-1 min-w-0 pr-8">
                    <div className="font-medium truncate">
                      {thread.title || 'New conversation'}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatDate(thread.updated_at)}
                    </div>
                  </div>
                  <button
                    onClick={(e) => deleteThread(thread.id, e)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 opacity-0 group-hover:opacity-100 hover:bg-red-100 dark:hover:bg-red-900/20 rounded transition-opacity"
                    title="Delete conversation"
                  >
                    <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="p-4 border-t border-border space-y-2">
          <Link
            href="/memory"
            className="block w-full px-4 py-2 text-center text-sm border border-border rounded-md hover:bg-accent"
          >
            Pinned Memory
          </Link>
          <Link
            href="/settings"
            className="block w-full px-4 py-2 text-center text-sm border border-border rounded-md hover:bg-accent"
          >
            Settings
          </Link>
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        {currentThread ? (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    'flex gap-3',
                    message.role === 'user' && 'justify-end'
                  )}
                >
                  <div
                    className={cn(
                      'max-w-2xl rounded-lg px-4 py-3',
                      message.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : message.role === 'assistant'
                        ? 'bg-muted'
                        : 'bg-secondary text-xs'
                    )}
                  >
                    {message.role === 'tool' ? (
                      <>
                        <div className="font-mono text-xs text-muted-foreground mb-1">
                          Tool: {message.name}
                        </div>
                        <pre className="whitespace-pre-wrap text-xs">
                          {message.content}
                        </pre>
                      </>
                    ) : (
                      <div className="whitespace-pre-wrap">{message.content}</div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex gap-3">
                  <div className="bg-muted rounded-lg px-4 py-3">
                    <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-border p-4">
              <div className="max-w-4xl mx-auto flex gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="Type your message..."
                  rows={1}
                  className="flex-1 px-4 py-3 border border-border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                  disabled={loading}
                />
                <button
                  onClick={sendMessage}
                  disabled={!input.trim() || loading}
                  className="px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="w-5 h-5" />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <MessageSquare className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Select a conversation or create a new one</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
