import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Sparkles,
  Send,
  User,
  Bot,
  FileText,
  Trash2,
  AlertCircle,
  HelpCircle,
  Shield,
  Layers,
  ArrowRight,
  Plus,
  MessageSquare,
  Edit2,
  Check,
  X,
  Loader2,
} from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader } from '../components/primitives'
import { useAuth } from '../lib/auth'

const PROMPT_SUGGESTIONS = [
  'How does the RakshaAI blended risk score work?',
  'What is Card Testing attack typology and how is it detected?',
  'Explain the cost-sensitive loss optimization matrix and chargeback fees.',
  'What are the characteristics of Account Takeover (ATO)?',
]

const INITIAL_WELCOME = {
  id: 'welcome',
  role: 'assistant',
  content:
    'Hello! I am the **RakshaAI Risk & Fraud Analyst**. I can assist you with:\n\n- **Platform Architecture**: Dual XGBoost models & blended risk scoring\n- **Decision Thresholds**: `ALLOW`, `STEP_UP`, `HOLD`, and `BLOCK`\n- **Loss Optimization**: Potential loss formulas & dispute fee mitigation\n- **Threat Typologies**: Card Testing, Account Takeover (ATO), and Ring Risk\n\nHow can I help you analyze risk today?',
  sources: [],
}

const markdownComponents = {
  h1: ({ children }) => (
    <h1 className="mt-3 mb-2 text-base font-bold text-ink border-b border-line pb-1">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-3 mb-1.5 text-[14.5px] font-semibold text-ink">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-2.5 mb-1 text-sm font-semibold text-ink">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="mt-2 mb-1 text-[13px] font-semibold text-ink">
      {children}
    </h4>
  ),
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 leading-relaxed text-[13.5px] text-ink">
      {children}
    </p>
  ),
  ul: ({ children }) => (
    <ul className="my-2 list-disc pl-5 space-y-1 text-[13.5px] text-ink">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal pl-5 space-y-1 text-[13.5px] text-ink">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="leading-relaxed text-[13.5px] text-ink">
      {children}
    </li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-ink">
      {children}
    </strong>
  ),
  em: ({ children }) => (
    <em className="italic text-ink/90">
      {children}
    </em>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-trust bg-trust/5 px-3 py-1.5 rounded-r text-faint italic text-xs">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-line" />,
  code: ({ inline, className, children, ...props }) => {
    if (inline) {
      return (
        <code className="rounded bg-canvas/80 px-1.5 py-0.5 font-mono text-[12px] text-trust border border-line" {...props}>
          {children}
        </code>
      )
    }
    return (
      <code className="block font-mono text-xs text-ink" {...props}>
        {children}
      </code>
    )
  },
  pre: ({ children }) => (
    <pre className="my-2.5 overflow-x-auto rounded-lg border border-line bg-canvas p-3 font-mono text-xs text-ink">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-line bg-paper/80 shadow-sm">
      <table className="min-w-full divide-y divide-line border-collapse text-left text-xs">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-canvas/90 font-semibold text-ink">
      {children}
    </thead>
  ),
  th: ({ children }) => (
    <th className="border-r border-line last:border-r-0 px-3.5 py-2 text-left font-semibold text-[12px] text-ink whitespace-nowrap bg-canvas/60">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-t border-r border-line last:border-r-0 px-3.5 py-2 text-[12px] text-muted align-top">
      {children}
    </td>
  ),
  tr: ({ children }) => (
    <tr className="even:bg-canvas/20 hover:bg-canvas/50 transition-colors">
      {children}
    </tr>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium text-trust hover:underline">
      {children}
    </a>
  ),
}

export default function AIAnalyst() {
  const { org } = useAuth()
  const [conversations, setConversations] = useState([])
  const [activeConvId, setActiveConvId] = useState(null)
  const [messages, setMessages] = useState([INITIAL_WELCOME])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState(null)

  // Renaming state
  const [editingId, setEditingId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')

  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, isLoading])

  // Load conversations list
  const loadConversations = useCallback(async (selectTargetId = null) => {
    try {
      const list = await api.aiAnalystConversations()
      setConversations(list || [])

      // Determine active conversation
      const savedId = localStorage.getItem('rakshaai.active_conversation_id')
      let targetId = selectTargetId || (savedId ? parseInt(savedId, 10) : null)

      if (targetId && list && list.some((c) => c.id === targetId)) {
        loadConversationMessages(targetId)
      } else if (list && list.length > 0) {
        loadConversationMessages(list[0].id)
      } else {
        setActiveConvId(null)
        setMessages([INITIAL_WELCOME])
      }
    } catch (err) {
      console.error('Failed to load conversations:', err)
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // Load specific conversation messages
  const loadConversationMessages = async (convId) => {
    if (!convId) return
    setActiveConvId(convId)
    localStorage.setItem('rakshaai.active_conversation_id', String(convId))
    setLoadingHistory(true)
    setError(null)

    try {
      const data = await api.getAIConversation(convId)
      if (data && data.messages && data.messages.length > 0) {
        setMessages(data.messages)
      } else {
        setMessages([INITIAL_WELCOME])
      }
    } catch (err) {
      console.error('Failed to fetch conversation history:', err)
      setError('Could not load chat messages.')
      setMessages([INITIAL_WELCOME])
    } finally {
      setLoadingHistory(false)
    }
  }

  // Create New Chat
  const handleNewChat = async () => {
    try {
      const newConv = await api.createAIConversation({ title: 'New Chat' })
      setActiveConvId(newConv.id)
      localStorage.setItem('rakshaai.active_conversation_id', String(newConv.id))
      setMessages([INITIAL_WELCOME])
      setInput('')
      setError(null)
      loadConversations(newConv.id)
      inputRef.current?.focus()
    } catch (err) {
      console.error('Failed to create new chat:', err)
      setError('Could not create new chat.')
    }
  }

  // Rename Conversation
  const startEditing = (c, e) => {
    e.stopPropagation()
    setEditingId(c.id)
    setEditingTitle(c.title)
  }

  const saveEditing = async (c, e) => {
    e.stopPropagation()
    const trimmed = editingTitle.trim()
    if (!trimmed || trimmed === c.title) {
      setEditingId(null)
      return
    }

    try {
      await api.renameAIConversation(c.id, trimmed)
      setConversations((prev) =>
        prev.map((item) => (item.id === c.id ? { ...item, title: trimmed } : item))
      )
    } catch (err) {
      console.error('Failed to rename conversation:', err)
    } finally {
      setEditingId(null)
    }
  }

  const cancelEditing = (e) => {
    e.stopPropagation()
    setEditingId(null)
  }

  // Delete Conversation
  const handleDelete = async (convId, e) => {
    e.stopPropagation()
    try {
      await api.deleteAIConversation(convId)
      const remaining = conversations.filter((c) => c.id !== convId)
      setConversations(remaining)

      if (activeConvId === convId) {
        if (remaining.length > 0) {
          loadConversationMessages(remaining[0].id)
        } else {
          setActiveConvId(null)
          localStorage.removeItem('rakshaai.active_conversation_id')
          setMessages([INITIAL_WELCOME])
        }
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
      setError('Could not delete chat.')
    }
  }

  // Clear Current Conversation
  const handleClearCurrent = async () => {
    if (!activeConvId) {
      setMessages([INITIAL_WELCOME])
      return
    }

    try {
      await api.clearAIConversation(activeConvId)
      setMessages([INITIAL_WELCOME])
      setError(null)
      setInput('')
      const list = await api.aiAnalystConversations()
      setConversations(list || [])
    } catch (err) {
      console.error('Failed to clear conversation:', err)
      setError('Could not clear current conversation.')
    }
  }

  // Send query
  const handleSend = async (queryText) => {
    const q = (queryText || input).trim()
    if (!q || isLoading) return

    setError(null)
    const userMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: q,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMsg])
    if (!queryText) setInput('')
    setIsLoading(true)

    try {
      const res = await api.aiAnalystQuery({
        query: q,
        conversation_id: activeConvId,
        top_k: 5,
      })

      if (res.conversation_id && res.conversation_id !== activeConvId) {
        setActiveConvId(res.conversation_id)
        localStorage.setItem('rakshaai.active_conversation_id', String(res.conversation_id))
      }

      const botMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: res.answer || "I don't have enough information in the system context to answer that.",
        sources: res.sources || [],
        retrieved_chunks: res.retrieved_chunks || 0,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, botMsg])

      const updatedList = await api.aiAnalystConversations()
      setConversations(updatedList || [])
    } catch (err) {
      console.error('AI Analyst query error:', err)
      setError(err.message || 'Failed to get response from AI Analyst.')
      const errorMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: 'Sorry, I encountered an error communicating with the AI Analyst service. Please check backend logs or your connection.',
        isError: true,
        sources: [],
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col pb-12">
      <PageHeader
        title="AI Risk Analyst"
        subtitle="RAG-grounded intelligence for merchant risk decisions."
        actions={
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-full border border-trust/30 bg-trust/10 px-2.5 py-1 text-[11.5px] font-medium text-trust">
              <Sparkles size={13} />
              LLM Grounded
            </span>
            <button
              onClick={handleClearCurrent}
              type="button"
              className="flex items-center gap-1.5 rounded-md border border-line bg-paper px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-canvas hover:text-ink"
              title="Clear messages in current chat"
            >
              <Trash2 size={13} />
              Clear Chat
            </button>
          </div>
        }
      />

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* ChatGPT-style Conversation Sidebar (3 cols) */}
        <div className="lg:col-span-3 flex flex-col space-y-3">
          <button
            onClick={handleNewChat}
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-trust/40 bg-trust/10 px-4 py-2.5 text-xs font-semibold text-trust transition-all hover:bg-trust hover:text-ink-900 shadow-sm"
          >
            <Plus size={15} strokeWidth={2.5} />
            New Chat
          </button>

          <Card className="flex flex-col h-[calc(100vh-280px)] min-h-[460px] border-line p-2 overflow-hidden bg-paper/60">
            <div className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted flex items-center justify-between border-b border-line/60 pb-2">
              <span>Recent Conversations</span>
              <span className="text-[10px] text-faint font-normal">{conversations.length} total</span>
            </div>

            <div className="mt-2 flex-1 overflow-y-auto space-y-1 pr-1">
              {conversations.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-xs text-faint">
                  <MessageSquare size={24} className="mb-2 text-faint/50" />
                  <span>No chat sessions yet.</span>
                  <span className="mt-0.5 text-[11px]">Click "New Chat" to begin.</span>
                </div>
              ) : (
                conversations.map((c) => {
                  const isActive = activeConvId === c.id
                  const isEditing = editingId === c.id

                  return (
                    <div
                      key={c.id}
                      onClick={() => !isEditing && loadConversationMessages(c.id)}
                      className={`group relative flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-xs transition-all cursor-pointer ${
                        isActive
                          ? 'bg-trust/15 text-trust font-medium border border-trust/30'
                          : 'text-muted hover:bg-canvas hover:text-ink border border-transparent'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <MessageSquare
                          size={14}
                          className={`shrink-0 ${isActive ? 'text-trust' : 'text-faint group-hover:text-muted'}`}
                        />

                        {isEditing ? (
                          <div className="flex items-center gap-1 flex-1 min-w-0" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="text"
                              value={editingTitle}
                              onChange={(e) => setEditingTitle(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveEditing(c, e)
                                if (e.key === 'Escape') cancelEditing(e)
                              }}
                              autoFocus
                              className="w-full rounded border border-trust bg-canvas px-1.5 py-0.5 text-xs text-ink focus:outline-none"
                            />
                            <button
                              type="button"
                              onClick={(e) => saveEditing(c, e)}
                              className="p-0.5 hover:text-trust"
                              title="Save"
                            >
                              <Check size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={cancelEditing}
                              className="p-0.5 hover:text-signal"
                              title="Cancel"
                            >
                              <X size={13} />
                            </button>
                          </div>
                        ) : (
                          <span className="truncate text-[12.5px] leading-tight">
                            {c.title || 'Untitled Chat'}
                          </span>
                        )}
                      </div>

                      {!isEditing && (
                        <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={(e) => startEditing(c, e)}
                            className="p-1 text-faint hover:text-ink rounded transition-colors"
                            title="Rename"
                          >
                            <Edit2 size={12} />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => handleDelete(c.id, e)}
                            className="p-1 text-faint hover:text-signal rounded transition-colors"
                            title="Delete"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </Card>
        </div>

        {/* Main Chat Panel (6 cols) */}
        <div className="lg:col-span-6 flex flex-col">
          <Card className="flex h-[calc(100vh-220px)] min-h-[520px] flex-col overflow-hidden border-line p-0">
            {/* Conversation Area */}
            <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
              {loadingHistory ? (
                <div className="flex h-full items-center justify-center text-xs text-faint gap-2">
                  <Loader2 size={16} className="animate-spin text-trust" />
                  <span>Loading chat history…</span>
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  {messages.map((msg, index) => {
                    const isUser = msg.role === 'user'
                    const rawContent = msg.content || msg.text || ''

                    return (
                      <motion.div
                        key={msg.id || index}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18 }}
                        className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                      >
                        {!isUser && (
                          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-trust/15 text-trust">
                            <Bot size={17} strokeWidth={2.2} />
                          </div>
                        )}

                        <div
                          className={`max-w-[85%] rounded-xl px-4 py-3 text-[13.5px] leading-relaxed shadow-sm ${
                            isUser
                              ? 'bg-trust text-ink-900 font-medium whitespace-pre-wrap'
                              : msg.isError
                              ? 'border border-signal/30 bg-signal/10 text-signal'
                              : 'border border-line bg-paper text-ink'
                          }`}
                        >
                          {isUser ? (
                            rawContent
                          ) : (
                            <div className="prose-chat">
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={markdownComponents}
                              >
                                {rawContent}
                              </ReactMarkdown>
                            </div>
                          )}

                          {/* Grounding Sources Panel */}
                          {msg.sources && msg.sources.length > 0 && (
                            <div className="mt-3.5 border-t border-line/60 pt-2.5">
                              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                                <Layers size={12} className="text-trust" />
                                Grounding Sources ({msg.sources.length})
                              </div>
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {msg.sources.map((src, i) => {
                                  const title =
                                    typeof src === 'string'
                                      ? src
                                      : src.title || `Document ${i + 1}`
                                  const score =
                                    typeof src === 'object' && Number.isFinite(src.score)
                                      ? src.score
                                      : null

                                  return (
                                    <span
                                      key={src.id || i}
                                      className="inline-flex items-center gap-1.5 rounded-md border border-line bg-canvas/60 px-2.5 py-1 text-[11px] text-faint"
                                      title={src.doc_type ? `Type: ${src.doc_type}` : undefined}
                                    >
                                      <FileText size={11} className="text-trust shrink-0" />
                                      <span className="font-medium text-ink truncate max-w-[200px]">
                                        {title}
                                      </span>
                                      {score !== null && score > 0 && (
                                        <span className="tnum rounded bg-trust/15 px-1 py-0.5 text-[9.5px] font-bold text-trust shrink-0">
                                          {(score * 100).toFixed(0)}% match
                                        </span>
                                      )}
                                    </span>
                                  )
                                })}
                              </div>
                            </div>
                          )}
                        </div>

                        {isUser && (
                          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-ink-900 text-white">
                            <User size={16} />
                          </div>
                        )}
                      </motion.div>
                    )
                  })}
                </AnimatePresence>
              )}

              {/* Thinking indicator */}
              {isLoading && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-3"
                >
                  <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-trust/15 text-trust">
                    <Bot size={17} strokeWidth={2.2} />
                  </div>
                  <div className="flex items-center gap-2 rounded-xl border border-line bg-paper px-4 py-3 text-xs text-muted shadow-sm">
                    <span className="flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-trust [animation-delay:-0.3s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-trust [animation-delay:-0.15s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-trust" />
                    </span>
                    <span>Analyzing system context &amp; generating grounded response…</span>
                  </div>
                </motion.div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input Bar */}
            <div className="border-t border-line bg-paper p-3 sm:p-4">
              {error && (
                <div className="mb-3 flex items-center gap-2 rounded-md border border-signal/30 bg-signal/10 px-3 py-2 text-xs text-signal">
                  <AlertCircle size={14} className="shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="relative flex items-center">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about fraud patterns, scoring models, or merchant policy…"
                  disabled={isLoading}
                  className="w-full rounded-lg border border-line bg-canvas px-4 py-3 pr-12 text-[13.5px] text-ink placeholder:text-faint focus:border-trust focus:outline-none focus:ring-1 focus:ring-trust disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isLoading}
                  className="absolute right-2 grid h-8 w-8 place-items-center rounded-md bg-trust text-ink-900 transition-opacity hover:opacity-90 disabled:opacity-30"
                  aria-label="Send query"
                >
                  <Send size={15} />
                </button>
              </div>

              <div className="mt-2 flex items-center justify-between text-[11px] text-faint">
                <span>Press Enter to send</span>
                <span className="flex items-center gap-1">
                  <Shield size={11} />
                  Privacy protected &middot; Tenant isolated
                </span>
              </div>
            </div>
          </Card>
        </div>

        {/* Reference & Suggestions Sidebar (3 cols) */}
        <div className="lg:col-span-3 space-y-4">
          <Card className="border-line p-4">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
              <HelpCircle size={16} className="text-trust" />
              Suggested Inquiries
            </div>
            <p className="mt-1 text-xs text-faint">
              Click any sample prompt to run a grounded RAG analysis:
            </p>
            <div className="mt-3 space-y-2">
              {PROMPT_SUGGESTIONS.map((s, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(s)}
                  disabled={isLoading}
                  className="group flex w-full items-start gap-2 rounded-lg border border-line/70 bg-canvas/40 p-2.5 text-left text-xs text-muted transition-all hover:border-trust/50 hover:bg-canvas hover:text-ink disabled:opacity-50"
                >
                  <ArrowRight
                    size={13}
                    className="mt-0.5 shrink-0 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-trust"
                  />
                  <span>{s}</span>
                </button>
              ))}
            </div>
          </Card>

          <Card className="border-line p-4">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
              <Shield size={16} className="text-trust" />
              Grounding Rules
            </div>
            <ul className="mt-2 space-y-1.5 text-xs text-faint">
              <li className="flex items-start gap-1.5">
                <span className="text-trust">&bull;</span>
                Answers are grounded strictly in indexed platform knowledge and merchant policies.
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-trust">&bull;</span>
                Multi-turn conversation history is preserved across chats.
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-trust">&bull;</span>
                Cross-tenant isolation ensures your data is never accessible to other merchants.
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-trust">&bull;</span>
                Credentials and secret tokens are automatically redacted.
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  )
}
