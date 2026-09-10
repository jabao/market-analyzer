import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { portfolioApi, plaidApi } from '../services/api'
import { Briefcase, RefreshCw, Eye, TrendingUp, TrendingDown, DollarSign, PieChart, Link2, Unlink, Plus } from 'lucide-react'

interface Holding {
  id: number
  ticker_key: string
  ticker: string
  stock_name: string
  shares: number
  avg_purchase_price: number | null
  current_price: number | null
  cost_basis: number
  current_value: number | null
  gain_loss: number | null
  gain_loss_pct: number | null
  brokerage: string
}

interface Transaction {
  id: number
  date: string
  shares: number
  price: number
  total_value: number
  brokerage: string
}

interface LinkedAccount {
  id: number
  institution_name: string
  institution_id: string | null
  item_id: string
  logo: string | null
  cash_balance: number
  total_assets: number
  linked_at: string | null
  last_refreshed_at: string | null
}

const formatCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined || isNaN(value)) return '—'
  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absValue >= 1e12) return `${sign}$${(absValue / 1e12).toFixed(2)}T`
  if (absValue >= 1e9) return `${sign}$${(absValue / 1e9).toFixed(2)}B`
  if (absValue >= 1e6) return `${sign}$${(absValue / 1e6).toFixed(2)}M`
  if (absValue >= 1e3) return `${sign}$${(absValue / 1e3).toFixed(2)}K`
  return `${sign}$${absValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function PortfolioPage() {
  const queryClient = useQueryClient()
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [deleteTxnId, setDeleteTxnId] = useState('')
  const [isRefreshingAll, setIsRefreshingAll] = useState(false)
  const [isLinking, setIsLinking] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const { data: summary, isLoading: summaryLoading, error: summaryError } = useQuery({
    queryKey: ['portfolioSummary'],
    queryFn: portfolioApi.getSummary,
    refetchInterval: 30000,
  })

  const { data: accounts = [] } = useQuery({
    queryKey: ['plaidAccounts'],
    queryFn: plaidApi.getAccounts,
  })

  const { data: plaidConfig } = useQuery({
    queryKey: ['plaidConfig'],
    queryFn: plaidApi.getConfig,
  })

  const { data: transactions = [] } = useQuery({
    queryKey: ['transactions', selectedTicker],
    queryFn: () => portfolioApi.getTransactions(selectedTicker!),
    enabled: !!selectedTicker,
  })

  const refreshMutation = useMutation({
    mutationFn: portfolioApi.refreshPrices,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolioSummary'] })
      setToast({
        type: 'success',
        message: 'Prices refreshed successfully',
      })
      setTimeout(() => setToast(null), 3000)
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to refresh prices'
      setToast({
        type: 'error',
        message: `Refresh failed: ${message}`,
      })
      setTimeout(() => setToast(null), 5000)
    },
  })

  const deleteHoldingMutation = useMutation({
    mutationFn: portfolioApi.deleteHolding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolioSummary'] })
    },
  })

  const deleteTickerMutation = useMutation({
    mutationFn: portfolioApi.deleteTickerHoldings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolioSummary'] })
      setDeleteConfirm(null)
    },
  })

  const unlinkAccountMutation = useMutation({
    mutationFn: plaidApi.unlinkAccount,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plaidAccounts'] })
      queryClient.invalidateQueries({ queryKey: ['portfolioSummary'] })
      setToast({
        type: 'success',
        message: 'Brokerage account disconnected successfully',
      })
      setTimeout(() => setToast(null), 5000)
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to disconnect account'
      setToast({
        type: 'error',
        message: `Disconnect failed: ${message}`,
      })
      setTimeout(() => setToast(null), 5000)
    },
  })

  const exchangeTokenMutation = useMutation({
    mutationFn: ({ publicToken, metadata }: { publicToken: string; metadata: any }) =>
      plaidApi.exchangeToken(publicToken, metadata),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plaidAccounts'] })
      queryClient.invalidateQueries({ queryKey: ['portfolioSummary'] })
      setToast({
        type: 'success',
        message: `Successfully connected ${data.institution_name}. Importing holdings...`,
      })
      setTimeout(() => setToast(null), 5000)
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to connect brokerage'
      setToast({
        type: 'error',
        message: `Connection failed: ${message}`,
      })
      setTimeout(() => setToast(null), 5000)
    },
    onSettled: () => {
      setIsLinking(false)
    },
  })

  const refreshAllMutation = useMutation({
    mutationFn: plaidApi.refreshAllAccounts,
    onMutate: () => {
      setIsRefreshingAll(true)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plaidAccounts'] })
      queryClient.invalidateQueries({ queryKey: ['portfolioSummary'] })
      
      if (data.failed === 0) {
        setToast({
          type: 'success',
          message: `Successfully synced all ${data.successful} brokerage${data.successful !== 1 ? 's' : ''}`,
        })
      } else {
        setToast({
          type: 'error',
          message: `Synced ${data.successful} of ${data.total_accounts} brokerages. ${data.failed} failed.`,
        })
      }
      setTimeout(() => setToast(null), 5000)
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to sync brokerages'
      setToast({
        type: 'error',
        message: `Sync failed: ${message}`,
      })
      setTimeout(() => setToast(null), 5000)
    },
    onSettled: () => {
      setIsRefreshingAll(false)
    },
  })

  const handleDeleteTxn = () => {
    const id = parseInt(deleteTxnId)
    if (id) {
      deleteHoldingMutation.mutate(id)
      setDeleteTxnId('')
    }
  }

  const handleAddBrokerage = async () => {
    if (!plaidConfig?.configured) {
      setToast({
        type: 'error',
        message: 'Plaid is not configured. Please set PLAID_CLIENT_ID and PLAID_SECRET environment variables.',
      })
      setTimeout(() => setToast(null), 5000)
      return
    }

    setIsLinking(true)
    try {
      // Create link token
      const clientUserId = `user_${Date.now()}`
      const linkTokenData = await plaidApi.createLinkToken(clientUserId)
      
      // Open Plaid Link in a new window using Plaid's Link library
      const Plaid = (window as any).Plaid
      if (!Plaid) {
        throw new Error('Plaid Link library not loaded')
      }

      const handler = Plaid.create({
        token: linkTokenData.link_token,
        onSuccess: (publicToken: string, metadata: any) => {
          exchangeTokenMutation.mutate({ publicToken, metadata })
        },
        onExit: (err: any, metadata: any) => {
          setIsLinking(false)
          if (err) {
            setToast({
              type: 'error',
              message: `Plaid Link exited with error: ${err.error_message || err.error_code}`,
            })
            setTimeout(() => setToast(null), 5000)
          }
        },
      })

      handler.open()
    } catch (error) {
      setIsLinking(false)
      const message = error instanceof Error ? error.message : 'Failed to initialize Plaid Link'
      setToast({
        type: 'error',
        message: `Failed to connect brokerage: ${message}`,
      })
      setTimeout(() => setToast(null), 5000)
    }
  }

  const holdings = summary?.holdings || []
  const totalGainLoss = summary?.net_gain_loss || 0
  const isPositive = totalGainLoss >= 0

  if (summaryLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    )
  }

  if (summaryError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
        <div className="text-red-600 text-lg font-semibold mb-2">Failed to load portfolio</div>
        <div className="text-red-500 text-sm mb-4">{summaryError instanceof Error ? summaryError.message : 'Unknown error'}</div>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-6 py-4 rounded-lg shadow-lg flex items-center space-x-3 ${
          toast.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
        }`}>
          {toast.type === 'success' ? (
            <TrendingUp className="h-5 w-5" />
          ) : (
            <RefreshCw className="h-5 w-5" />
          )}
          <span className="font-medium">{toast.message}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-4 text-white hover:text-gray-200"
          >
            ×
          </button>
        </div>
      )}
      
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center">
            <Briefcase className="mr-2 h-6 w-6 text-blue-600" />
            Portfolio Tracker
          </h1>
          <p className="text-slate-600 mt-1">
            Track your stock portfolio with real-time price updates
          </p>
        </div>
        <button
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Total Holdings</p>
              <p className="text-2xl font-bold text-slate-900">{summary?.total_holdings || 0}</p>
            </div>
            <PieChart className="h-8 w-8 text-slate-400" />
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Total Assets</p>
              <p className="text-2xl font-bold text-slate-900">{formatCurrency(summary?.total_assets)}</p>
            </div>
            <DollarSign className="h-8 w-8 text-slate-400" />
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Cash</p>
              <p className="text-2xl font-bold text-slate-900">{formatCurrency(summary?.total_cash)}</p>
            </div>
            <DollarSign className="h-8 w-8 text-green-400" />
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Invested Value</p>
              <p className="text-2xl font-bold text-slate-900">{formatCurrency(summary?.invested_value)}</p>
            </div>
            <Briefcase className="h-8 w-8 text-slate-400" />
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Net Gain/Loss</p>
              <p className={`text-2xl font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                {isPositive ? '+' : ''}{formatCurrency(totalGainLoss)}
              </p>
              <p className={`text-xs ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                {isPositive ? '+' : ''}{(summary?.net_gain_loss_pct || 0).toFixed(2)}%
              </p>
            </div>
            {isPositive ? (
              <TrendingUp className="h-8 w-8 text-green-400" />
            ) : (
              <TrendingDown className="h-8 w-8 text-red-400" />
            )}
          </div>
        </div>
      </div>

      {/* Linked Accounts */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-slate-900 flex items-center">
            <Link2 className="h-5 w-5 mr-2" />
            Connected Brokerages
          </h2>
          <div className="flex space-x-2">
            {accounts.length > 0 && (
              <button
                onClick={() => refreshAllMutation.mutate()}
                disabled={isRefreshingAll}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshingAll ? 'animate-spin' : ''}`} />
                {isRefreshingAll ? 'Syncing...' : 'Sync All'}
              </button>
            )}
            <button
              onClick={handleAddBrokerage}
              disabled={isLinking}
              className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              <Plus className={`h-4 w-4 mr-2 ${isLinking ? 'animate-spin' : ''}`} />
              {isLinking ? 'Connecting...' : 'Add New Brokerage'}
            </button>
          </div>
        </div>
        {accounts.length > 0 ? (
          <div className="space-y-3">
            {accounts.map((account: LinkedAccount) => (
              <div key={account.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                <div className="flex items-center space-x-4">
                  {account.logo && (
                    <img 
                      src={`data:image/png;base64,${account.logo}`} 
                      alt={account.institution_name}
                      className="h-12 w-12 object-contain"
                    />
                  )}
                  <div>
                    <p className="font-semibold text-slate-900">{account.institution_name}</p>
                    <p className="text-xs text-slate-500">
                      Last synced: {account.last_refreshed_at || account.linked_at || 'Never'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-6">
                  <div className="text-right">
                    <p className="text-xs text-slate-500">Total Assets</p>
                    <p className="font-semibold">{formatCurrency(account.total_assets)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-500">Cash</p>
                    <p className="font-semibold">{formatCurrency(account.cash_balance)}</p>
                  </div>
                  <button
                    onClick={() => unlinkAccountMutation.mutate(account.item_id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="Disconnect"
                  >
                    <Unlink className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-slate-500">
            No brokerages connected yet. Click "Add New Brokerage" to connect your first account.
          </div>
        )}
      </div>

      {/* Plaid Link - Simplified notice */}
      {plaidConfig && !plaidConfig.configured && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-sm text-amber-800">
            <strong>Plaid not configured.</strong> Set PLAID_CLIENT_ID and PLAID_SECRET environment variables to enable brokerage imports.
          </p>
        </div>
      )}

      {/* Holdings Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">Your Holdings</h2>
        </div>

        {holdings.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            No holdings yet. Connect a brokerage above to sync your portfolio.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Ticker</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Shares</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Avg Price</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Current Price</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Cost Basis</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Current Value</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Gain/Loss</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {holdings.map((holding: Holding) => {
                  const gainLoss = holding.gain_loss
                  const isPos = gainLoss !== null && gainLoss >= 0
                  return (
                    <tr key={holding.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <div>
                          <div className="font-mono font-semibold">{holding.ticker}</div>
                          <div className="text-xs text-slate-500">{holding.stock_name}</div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">{holding.shares?.toFixed(4) || '0'}</td>
                      <td className="px-4 py-3 text-sm">{formatCurrency(holding.avg_purchase_price)}</td>
                      <td className="px-4 py-3 text-sm">{formatCurrency(holding.current_price)}</td>
                      <td className="px-4 py-3 text-sm">{formatCurrency(holding.cost_basis)}</td>
                      <td className="px-4 py-3 text-sm">{formatCurrency(holding.current_value)}</td>
                      <td className="px-4 py-3">
                        <div className={`text-sm font-medium ${isPos ? 'text-green-600' : gainLoss === null || gainLoss === undefined ? 'text-slate-500' : 'text-red-600'}`}>
                          {gainLoss !== null && gainLoss !== undefined ? `${isPos ? '+' : ''}${formatCurrency(gainLoss)}` : '—'}
                        </div>
                        <div className={`text-xs ${isPos ? 'text-green-600' : 'text-red-600'}`}>
                          {holding.gain_loss_pct !== null && holding.gain_loss_pct !== undefined ? `${isPos ? '+' : ''}${holding.gain_loss_pct.toFixed(2)}%` : ''}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="relative inline-block">
                          <button
                            onClick={() => setSelectedTicker(selectedTicker === holding.ticker ? null : holding.ticker)}
                            className="peer p-1 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-slate-900 text-white text-xs rounded shadow-lg opacity-0 peer-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-50 hidden peer-hover:block">
                            Show Transactions
                            <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-slate-900"></div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <p className="text-sm text-red-800 mb-3">
            Are you sure you want to delete all positions for <strong>{deleteConfirm}</strong>? This cannot be undone.
          </p>
          <div className="flex items-center space-x-3">
            <input
              type="text"
              placeholder={`Type ${deleteConfirm} to confirm`}
              value={deleteConfirm === deleteConfirm ? '' : ''}
              onChange={() => {}}
              className="px-3 py-1.5 border border-red-300 rounded-lg text-sm"
              onKeyDown={(e) => {
                if (e.currentTarget.value === deleteConfirm && e.key === 'Enter') {
                  deleteTickerMutation.mutate(deleteConfirm)
                }
              }}
            />
            <button
              onClick={() => {
                const input = document.querySelector('input[placeholder^="Type"]') as HTMLInputElement
                if (input && input.value === deleteConfirm) {
                  deleteTickerMutation.mutate(deleteConfirm)
                }
              }}
              className="px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm transition-colors"
            >
              Confirm Delete
            </button>
            <button
              onClick={() => setDeleteConfirm(null)}
              className="px-3 py-1.5 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 text-sm transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Transactions View */}
      {selectedTicker && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Transaction History: {selectedTicker}
            </h2>
            <button
              onClick={() => setSelectedTicker(null)}
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              ← Back to Portfolio
            </button>
          </div>

          {transactions.length === 0 ? (
            <p className="text-slate-500 text-center py-8">No transactions found.</p>
          ) : (
            <div>
              <div className="overflow-x-auto mb-4">
                <table className="w-full">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600 uppercase">ID</th>
                      <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600 uppercase">Date</th>
                      <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600 uppercase">Shares</th>
                      <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600 uppercase">Price</th>
                      <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600 uppercase">Total Value</th>
                      <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600 uppercase">Brokerage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {transactions.map((txn: Transaction) => (
                      <tr key={txn.id} className="hover:bg-slate-50">
                        <td className="px-4 py-2 text-sm">{txn.id}</td>
                        <td className="px-4 py-2 text-sm">{txn.date}</td>
                        <td className="px-4 py-2 text-sm">{txn.shares}</td>
                        <td className="px-4 py-2 text-sm">{formatCurrency(txn.price)}</td>
                        <td className="px-4 py-2 text-sm">{formatCurrency(txn.total_value)}</td>
                        <td className="px-4 py-2 text-sm">{txn.brokerage}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center space-x-3 pt-4 border-t border-slate-200">
                <input
                  type="number"
                  placeholder="Transaction ID to delete"
                  value={deleteTxnId}
                  onChange={(e) => setDeleteTxnId(e.target.value)}
                  className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm w-48"
                />
                <button
                  onClick={handleDeleteTxn}
                  disabled={!deleteTxnId || deleteHoldingMutation.isPending}
                  className="px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm transition-colors"
                >
                  Delete Transaction
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
