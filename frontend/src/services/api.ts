import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Market API
export const marketApi = {
  getQuotes: () => api.get('/market/quotes').then(r => r.data),
  
  getScoredStocks: (weights?: {
    valuation: number
    profitability: number
    growth: number
    financial_health: number
  }) => api.post('/market/scored', { weights }).then(r => r.data),
  
  getStockDetails: (symbol: string) => 
    api.get(`/market/stock/${symbol}`).then(r => r.data),
  
  getStockHistory: (symbol: string, rangeKey: string = '6M') =>
    api.get(`/market/stock/${symbol}/history`, { params: { range_key: rangeKey } }).then(r => r.data),
  
  getPriceRanges: () => api.get('/market/ranges').then(r => r.data),
  
  refreshMarketData: () => api.post('/market/refresh').then(r => r.data),
}

// Portfolio API
export const portfolioApi = {
  getHoldings: () => api.get('/portfolio/holdings').then(r => r.data),
  
  getSummary: () => api.get('/portfolio/summary').then(r => r.data),
  
  addHolding: (data: {
    ticker: string
    shares: number
    purchase_date: string
    purchase_price: number
    brokerage?: string
  }) => api.post('/portfolio/holdings', data).then(r => r.data),
  
  getTransactions: (ticker: string) =>
    api.get(`/portfolio/holdings/${ticker}/transactions`).then(r => r.data),
  
  deleteHolding: (id: number) =>
    api.delete(`/portfolio/holdings/${id}`).then(r => r.data),
  
  deleteTickerHoldings: (ticker: string) =>
    api.delete(`/portfolio/holdings/ticker/${ticker}`).then(r => r.data),
  
  refreshPrices: () => api.post('/portfolio/refresh-prices').then(r => r.data),
}

// Plaid API
export const plaidApi = {
  getConfig: () => api.get('/plaid/config').then(r => r.data),
  
  createLinkToken: (clientUserId: string) =>
    api.post('/plaid/link-token', { client_user_id: clientUserId }).then(r => r.data),
  
  exchangeToken: (publicToken: string, metadata: any) =>
    api.post('/plaid/exchange', { public_token: publicToken, metadata }).then(r => r.data),
  
  getAccounts: () => api.get('/plaid/accounts').then(r => r.data),
  
  refreshAccount: (itemId: string) =>
    api.post(`/plaid/accounts/${itemId}/refresh`).then(r => r.data),
  
  refreshAllAccounts: () =>
    api.post('/plaid/accounts/refresh-all').then(r => r.data),
  
  unlinkAccount: (itemId: string) =>
    api.delete(`/plaid/accounts/${itemId}`).then(r => r.data),
}

// LLM API
export const llmApi = {
  getProviders: () => api.get('/llm/providers').then(r => r.data),
  
  analyzeSector: async (
    data: any,
    onChunk?: (chunk: string) => void
  ): Promise<string> => {
    if (data.stream) {
      const response = await fetch('/api/llm/sector-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      
      if (!response.body) throw new Error('No response body')
      
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let fullText = ''
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        
        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') return fullText
            if (data.startsWith('ERROR:')) throw new Error(data.slice(7))
            fullText += data
            if (onChunk) onChunk(data)
          }
        }
      }
      return fullText
    } else {
      const response = await api.post('/llm/sector-analysis', data)
      return response.data.content
    }
  },
  
  analyzeStocks: async (
    data: any,
    onChunk?: (chunk: string) => void
  ): Promise<string> => {
    if (data.stream) {
      const response = await fetch('/api/llm/stock-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      
      if (!response.body) throw new Error('No response body')
      
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let fullText = ''
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        
        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') return fullText
            if (data.startsWith('ERROR:')) throw new Error(data.slice(7))
            fullText += data
            if (onChunk) onChunk(data)
          }
        }
      }
      return fullText
    } else {
      const response = await api.post('/llm/stock-analysis', data)
      return response.data.content
    }
  },
}

export default api
