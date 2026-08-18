import { useState, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { llmApi } from '../services/api'
import { Bot, Send, Download, Zap, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

const RISK_OPTIONS = ['Conservative', 'Moderate', 'Aggressive', 'Very Aggressive']
const TIME_HORIZON_OPTIONS = [
  '1-3 months (short)',
  '6-12 months (medium)',
  '12+ months (long)',
  '3-5 years (very long)',
]
const INVEST_STYLE_OPTIONS = [
  'Value (cheap multiples)',
  'Growth (high growth)',
  'Balanced (GARP)',
  'Quality (high ROE, low debt)',
  'Income (dividend)',
  'Growth at Reasonable Price',
  'Quality Growth',
  'Deep Value',
]

export default function AIAssistantPage() {
  const [mode, setMode] = useState<'sector' | 'stock'>('sector')
  const [provider, setProvider] = useState<'claude' | 'openai'>('claude')
  const [apiKey, setApiKey] = useState('')
  const [streamEnabled, setStreamEnabled] = useState(true)
  const [showPrompts, setShowPrompts] = useState(false)
  const [copied, setCopied] = useState(false)
  const resultRef = useRef<HTMLDivElement>(null)

  // Sector form state
  const [sectorForm, setSectorForm] = useState({
    trends: '',
    news: '',
    risk_tolerance: 'Moderate',
    time_horizon: '6-12 months (medium)',
    investment_style: 'Balanced (GARP)',
    additional: '',
  })

  // Stock form state
  const [stockForm, setStockForm] = useState({
    tickers: '',
    thesis: '',
    trends_and_news: '',
    filters: '',
    additional: '',
    focus_sector: '',
    risk_tolerance: 'Moderate',
    time_horizon: '12+ months (long)',
    investment_style: 'Quality Growth',
    benchmark: 'S&P 500',
    num_picks: 3,
  })

  const [result, setResult] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [lastProvider, setLastProvider] = useState('')

  const { data: providers = [] } = useQuery({
    queryKey: ['llmProviders'],
    queryFn: llmApi.getProviders,
  })

  const sectorMutation = useMutation({
    mutationFn: async (data: any) => {
      setIsStreaming(true)
      setResult('')
      let fullResult = ''
      await llmApi.analyzeSector(data, (chunk) => {
        fullResult += chunk
        setResult(fullResult)
      })
      setIsStreaming(false)
      setLastProvider(provider)
      return fullResult
    },
  })

  const stockMutation = useMutation({
    mutationFn: async (data: any) => {
      setIsStreaming(true)
      setResult('')
      let fullResult = ''
      await llmApi.analyzeStocks(data, (chunk) => {
        fullResult += chunk
        setResult(fullResult)
      })
      setIsStreaming(false)
      setLastProvider(provider)
      return fullResult
    },
  })

  const handleSectorSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    sectorMutation.mutate({
      provider,
      api_key: apiKey || undefined,
      ...sectorForm,
      stream: streamEnabled,
    })
  }

  const handleStockSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    stockMutation.mutate({
      provider,
      api_key: apiKey || undefined,
      ...stockForm,
      stream: streamEnabled,
    })
  }

  const handleDownload = () => {
    const blob = new Blob([result], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${mode}_analysis_${provider}_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(result)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const currentProvider = providers.find(p => p.id === provider)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center">
          <Bot className="mr-2 h-6 w-6 text-purple-600" />
          AI Market Deep Dive Assistant
        </h1>
        <p className="text-slate-600 mt-1">
          Powered by <strong>Claude 4.8</strong> and <strong>GPT 5.5</strong>. Analysis based on your inputs and LLM knowledge.
        </p>
      </div>

      {/* Provider Selection */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">Model</label>
            <div className="space-y-2">
              {providers.map((p: any) => (
                <label key={p.id} className="flex items-center cursor-pointer">
                  <input
                    type="radio"
                    name="provider"
                    value={p.id}
                    checked={provider === p.id}
                    onChange={(e) => setProvider(e.target.value as 'claude' | 'openai')}
                    className="mr-2"
                  />
                  <span className="text-sm">
                    <strong>{p.display_name}</strong>
                    <span className="text-slate-500 ml-2 text-xs">{p.default_model}</span>
                  </span>
                </label>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-2">
              ℹ️ No market data is sent to LLM
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={`sk-... (${currentProvider?.name} API key)`}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
            />
            <p className="text-xs text-slate-500 mt-1">
              Supports env vars or paste here
            </p>
          </div>

          <div className="flex items-end">
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={streamEnabled}
                onChange={(e) => setStreamEnabled(e.target.checked)}
                className="mr-2"
              />
              <span className="text-sm font-medium text-slate-700">
                <Zap className="inline h-4 w-4 mr-1" />
                Stream response
              </span>
            </label>
          </div>
        </div>
      </div>

      {/* Mode Selection */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-1">
        <div className="flex">
          <button
            onClick={() => setMode('sector')}
            className={`flex-1 py-3 px-4 text-sm font-medium rounded-lg transition-colors ${
              mode === 'sector'
                ? 'bg-purple-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            📈 Sector / Segment Recommendation
          </button>
          <button
            onClick={() => setMode('stock')}
            className={`flex-1 py-3 px-4 text-sm font-medium rounded-lg transition-colors ${
              mode === 'stock'
                ? 'bg-purple-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            🔍 Stock Deep Dive Picks
          </button>
        </div>
      </div>

      {/* Prompts Info */}
      <div className="bg-slate-50 rounded-xl border border-slate-200">
        <button
          onClick={() => setShowPrompts(!showPrompts)}
          className="w-full flex items-center justify-between p-4 text-left hover:bg-slate-100 transition-colors rounded-xl"
        >
          <span className="text-sm font-medium text-slate-700">
            📜 View Expert Prompts (read-only)
          </span>
          {showPrompts ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
        {showPrompts && (
          <div className="px-4 pb-4 border-t border-slate-200">
            <div className="mt-3 text-xs text-slate-600 space-y-2">
              <p>
                <strong>Sector Mode:</strong> Senior strategist persona analyzing macro trends, sector rotation, and providing ranked sector recommendations with risks and action plans.
              </p>
              <p>
                <strong>Stock Mode:</strong> Senior equity research analyst providing deep fundamental analysis, moat assessment, pro/con breakdown, and conviction levels for stock picks.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Forms */}
      {mode === 'sector' ? (
        <form onSubmit={handleSectorSubmit} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">Sector / Segment Recommendation</h2>
          <p className="text-sm text-slate-600">
            Provide trends and news; LLM will use its own knowledge (no live market data passed).
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Current Market Trends
              </label>
              <textarea
                value={sectorForm.trends}
                onChange={(e) => setSectorForm({ ...sectorForm, trends: e.target.value })}
                placeholder="e.g., AI CapEx boom, GLP-1 growth, reshoring, rate cuts..."
                rows={4}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Recent News / Events
              </label>
              <textarea
                value={sectorForm.news}
                onChange={(e) => setSectorForm({ ...sectorForm, news: e.target.value })}
                placeholder="e.g., Fed cut rates 25bps, NVDA earnings beat..."
                rows={4}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Additional Constraints / Preferences
            </label>
            <textarea
              value={sectorForm.additional}
              onChange={(e) => setSectorForm({ ...sectorForm, additional: e.target.value })}
              placeholder="e.g., Avoid crypto, focus on dividend, ESG..."
              rows={2}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Risk Tolerance</label>
              <select
                value={sectorForm.risk_tolerance}
                onChange={(e) => setSectorForm({ ...sectorForm, risk_tolerance: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                {RISK_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Time Horizon</label>
              <select
                value={sectorForm.time_horizon}
                onChange={(e) => setSectorForm({ ...sectorForm, time_horizon: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                {TIME_HORIZON_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Investment Style</label>
              <select
                value={sectorForm.investment_style}
                onChange={(e) => setSectorForm({ ...sectorForm, investment_style: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                {INVEST_STYLE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
          </div>

          <button
            type="submit"
            disabled={sectorMutation.isPending}
            className="w-full flex items-center justify-center px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors font-medium"
          >
            {sectorMutation.isPending ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Analyzing...
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Generate Sector Recommendation
              </>
            )}
          </button>
        </form>
      ) : (
        <form onSubmit={handleStockSubmit} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">Deep Dive Stock Picks</h2>
          <p className="text-sm text-slate-600">
            LLM uses its own knowledge + your thesis (no live fundamentals passed).
          </p>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Tickers (comma/space separated)
            </label>
            <input
              type="text"
              value={stockForm.tickers}
              onChange={(e) => setStockForm({ ...stockForm, tickers: e.target.value })}
              placeholder="e.g., NVDA, AAPL, MSFT, TSLA, or blank for general picks"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <p className="text-xs text-slate-500 mt-1">
              {stockForm.tickers ? `Tickers: ${stockForm.tickers}` : 'No tickers - LLM will suggest general quality picks'}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Investment Thesis
                </label>
                <textarea
                  value={stockForm.thesis}
                  onChange={(e) => setStockForm({ ...stockForm, thesis: e.target.value })}
                  placeholder="e.g., undervalued quality compounders, high growth AI beneficiaries..."
                  rows={3}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Trends / News
                </label>
                <textarea
                  value={stockForm.trends_and_news}
                  onChange={(e) => setStockForm({ ...stockForm, trends_and_news: e.target.value })}
                  placeholder="e.g., AI infra spending, FDA approvals, rate cuts..."
                  rows={2}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Must-have / Must-avoid filters
                </label>
                <textarea
                  value={stockForm.filters}
                  onChange={(e) => setStockForm({ ...stockForm, filters: e.target.value })}
                  placeholder="e.g., ROE >15%, no leveraged, avoid tobacco..."
                  rows={2}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Additional Notes
                </label>
                <textarea
                  value={stockForm.additional}
                  onChange={(e) => setStockForm({ ...stockForm, additional: e.target.value })}
                  placeholder="Anything else..."
                  rows={2}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Focus Sector(s)</label>
                <input
                  type="text"
                  value={stockForm.focus_sector}
                  onChange={(e) => setStockForm({ ...stockForm, focus_sector: e.target.value })}
                  placeholder="e.g., Technology, Healthcare"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Risk</label>
                  <select
                    value={stockForm.risk_tolerance}
                    onChange={(e) => setStockForm({ ...stockForm, risk_tolerance: e.target.value })}
                    className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    {RISK_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Style</label>
                  <select
                    value={stockForm.investment_style}
                    onChange={(e) => setStockForm({ ...stockForm, investment_style: e.target.value })}
                    className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    {INVEST_STYLE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Benchmark</label>
                  <input
                    type="text"
                    value={stockForm.benchmark}
                    onChange={(e) => setStockForm({ ...stockForm, benchmark: e.target.value })}
                    className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Num Picks</label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={stockForm.num_picks}
                    onChange={(e) => setStockForm({ ...stockForm, num_picks: parseInt(e.target.value) })}
                    className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={stockMutation.isPending}
            className="w-full flex items-center justify-center px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors font-medium"
          >
            {stockMutation.isPending ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Analyzing...
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Generate Stock Deep Dive
              </>
            )}
          </button>
        </form>
      )}

      {/* Results */}
      {result && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
            <h3 className="font-semibold text-slate-900 flex items-center">
              <Bot className="h-4 w-4 mr-2 text-purple-600" />
              Analysis Result {lastProvider && `— ${lastProvider}`}
              {isStreaming && <span className="ml-2 text-xs text-purple-600 animate-pulse">Streaming...</span>}
            </h3>
            <div className="flex space-x-2">
              <button
                onClick={handleCopy}
                className="flex items-center px-3 py-1.5 text-sm bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                {copied ? <Check className="h-4 w-4 mr-1" /> : <Copy className="h-4 w-4 mr-1" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
              <button
                onClick={handleDownload}
                className="flex items-center px-3 py-1.5 text-sm bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                <Download className="h-4 w-4 mr-1" />
                Download
              </button>
            </div>
          </div>
          <div ref={resultRef} className="p-6 prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-strong:text-slate-900">
            <ReactMarkdown>{result}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <p className="text-xs text-amber-800">
          <strong>⚠️ Disclaimer:</strong> This AI assistant is for informational/educational purposes only. Not financial advice. 
          Outputs are based on training knowledge and your inputs, may be outdated or hallucinated — verify facts.
        </p>
      </div>
    </div>
  )
}
