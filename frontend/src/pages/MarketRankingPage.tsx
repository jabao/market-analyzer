import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { marketApi } from '../services/api'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  flexRender,
  createColumnHelper,
  SortingState,
} from '@tanstack/react-table'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { RefreshCw, Search, TrendingUp, ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'

interface Stock {
  Ticker: string
  Company: string
  Score: number
  Valuation: number
  Profitability: number
  Growth: number
  Health: number
  Sector: string
  Price: number
  'Trailing P/E': number
  'Forward P/E': number
  PEG: number
  'P/B': number
  'Div Yield %': number
  Beta: number
  'Market Cap': number
}

interface StockDetails {
  symbol: string
  found: boolean
  name: string
  summary?: string
  sections: [string, [string, any, string][]][]
}

const columnHelper = createColumnHelper<Stock>()

const formatNumber = (value: number | null | undefined, decimals: number = 2): string => {
  if (value === null || value === undefined || isNaN(value)) return '—'
  return value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

const formatLarge = (value: number | null | undefined): string => {
  if (value === null || value === undefined || isNaN(value)) return '—'
  const absValue = Math.abs(value)
  if (absValue >= 1e12) return `$${(value / 1e12).toFixed(2)}T`
  if (absValue >= 1e9) return `$${(value / 1e9).toFixed(2)}B`
  if (absValue >= 1e6) return `$${(value / 1e6).toFixed(2)}M`
  if (absValue >= 1e3) return `$${(value / 1e3).toFixed(2)}K`
  return `$${value.toFixed(0)}`
}

const formatValue = (value: any, kind: string): string => {
  if (value === null || value === undefined) return '—'
  if (kind === 'text' || kind === 'url') return String(value)
  if (kind === 'price') return `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  if (kind === 'ratio') return formatNumber(Number(value), 2)
  if (kind === 'percent') return `${(Number(value) * 100).toFixed(2)}%`
  if (kind === 'large') return formatLarge(Number(value))
  if (kind === 'count') return formatLarge(Number(value)).replace('$', '')
  if (kind === 'int') return Math.round(Number(value)).toLocaleString()
  return String(value)
}

export default function MarketRankingPage() {
  const queryClient = useQueryClient()
  const [weights, setWeights] = useState({
    valuation: 40,
    profitability: 30,
    growth: 20,
    financial_health: 10,
  })
  const [sorting, setSorting] = useState<SortingState>([])
  const [selectedStock, setSelectedStock] = useState<string | null>(null)
  const [searchTicker, setSearchTicker] = useState('')
  const [priceRange, setPriceRange] = useState('6M')
  const [pageSize, setPageSize] = useState(20)

  const { data: rangesData } = useQuery({
    queryKey: ['priceRanges'],
    queryFn: marketApi.getPriceRanges,
  })

  const { data: stocks = [], isLoading, error } = useQuery({
    queryKey: ['scoredStocks', weights],
    queryFn: () => marketApi.getScoredStocks(weights),
  })

  const refreshMutation = useMutation({
    mutationFn: marketApi.refreshMarketData,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scoredStocks'] })
    },
  })

  const { data: stockDetails } = useQuery({
    queryKey: ['stockDetails', selectedStock],
    queryFn: () => marketApi.getStockDetails(selectedStock!),
    enabled: !!selectedStock,
  })

  const { data: priceHistory = [] } = useQuery({
    queryKey: ['priceHistory', selectedStock, priceRange],
    queryFn: () => marketApi.getStockHistory(selectedStock!, priceRange),
    enabled: !!selectedStock,
  })

  const columns = useMemo(
    () => [
      columnHelper.accessor('Ticker', {
        header: 'Ticker',
        cell: info => <span className="font-mono font-semibold">{info.getValue()}</span>,
      }),
      columnHelper.accessor('Company', {
        header: 'Company',
        cell: info => <span className="text-sm">{info.getValue()}</span>,
      }),
      columnHelper.accessor('Score', {
        header: 'Score',
        cell: info => (
          <span className="font-semibold text-blue-600">
            {formatNumber(info.getValue(), 1)}
          </span>
        ),
      }),
      columnHelper.accessor('Valuation', {
        header: 'Valuation',
        cell: info => formatNumber(info.getValue(), 1),
      }),
      columnHelper.accessor('Profitability', {
        header: 'Profitability',
        cell: info => formatNumber(info.getValue(), 1),
      }),
      columnHelper.accessor('Growth', {
        header: 'Growth',
        cell: info => formatNumber(info.getValue(), 1),
      }),
      columnHelper.accessor('Health', {
        header: 'Health',
        cell: info => formatNumber(info.getValue(), 1),
      }),
      columnHelper.accessor('Sector', {
        header: 'Sector',
        cell: info => <span className="text-sm">{info.getValue()}</span>,
      }),
      columnHelper.accessor('Price', {
        header: 'Price',
        cell: info => `$${formatNumber(info.getValue(), 2)}`,
      }),
      columnHelper.accessor('Trailing P/E', {
        header: 'Trailing P/E',
        cell: info => formatNumber(info.getValue(), 2),
      }),
      columnHelper.accessor('Forward P/E', {
        header: 'Forward P/E',
        cell: info => formatNumber(info.getValue(), 2),
      }),
      columnHelper.accessor('PEG', {
        header: 'PEG',
        cell: info => formatNumber(info.getValue(), 2),
      }),
      columnHelper.accessor('P/B', {
        header: 'P/B',
        cell: info => formatNumber(info.getValue(), 2),
      }),
      columnHelper.accessor('Div Yield %', {
        header: 'Div Yield %',
        cell: info => formatNumber(info.getValue(), 2),
      }),
      columnHelper.accessor('Beta', {
        header: 'Beta',
        cell: info => formatNumber(info.getValue(), 2),
      }),
      columnHelper.accessor('Market Cap', {
        header: 'Market Cap',
        cell: info => formatLarge(info.getValue()),
      }),
    ],
    []
  )

  const table = useReactTable({
    data: stocks,
    columns,
    state: { sorting, pagination: { pageIndex: 0, pageSize } },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  })

  const handleWeightChange = (dimension: keyof typeof weights, value: number) => {
    setWeights(prev => ({ ...prev, [dimension]: value }))
  }

  const handleRowClick = (stock: Stock) => {
    setSelectedStock(stock.Ticker)
    setSearchTicker('')
  }

  const handleSearch = () => {
    if (searchTicker.trim()) {
      setSelectedStock(searchTicker.trim().toUpperCase())
    }
  }

  const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0)
  const normalizedWeights = Object.fromEntries(
    Object.entries(weights).map(([k, v]) => [k, totalWeight > 0 ? (v / totalWeight) * 100 : 25])
  )

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center">
            <TrendingUp className="mr-2 h-6 w-6 text-blue-600" />
            Market Ranking
          </h1>
          <p className="text-slate-600 mt-1">
            S&P 500 stocks ranked by composite valuation score (higher = better)
          </p>
        </div>
        <button
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
          Refresh Data
        </button>
      </div>

      {/* Weights Panel */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Composite Score Weights</h2>
        <p className="text-sm text-slate-600 mb-4">
          Adjust the relative importance of each dimension. Values normalize automatically.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {Object.entries(weights).map(([key, value]) => {
            const labels: Record<string, string> = {
              valuation: 'Valuation (cheap)',
              profitability: 'Profitability',
              growth: 'Growth',
              financial_health: 'Financial health',
            }
            return (
              <div key={key}>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  {labels[key]}
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={value}
                  onChange={(e) => handleWeightChange(key as keyof typeof weights, Number(e.target.value))}
                  className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                />
                <div className="flex justify-between text-xs text-slate-500 mt-1">
                  <span>0%</span>
                  <span className="font-semibold text-slate-900">
                    {normalizedWeights[key].toFixed(0)}%
                  </span>
                  <span>100%</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Stocks Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex justify-between items-center">
          <div className="flex items-center space-x-4">
            <span className="text-sm text-slate-600">
              {stocks.length} stocks scored
            </span>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className="text-sm border border-slate-300 rounded-md px-2 py-1"
            >
              {[10, 20, 50].map(size => (
                <option key={size} value={size}>{size} rows</option>
              ))}
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 text-center">
            <RefreshCw className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-4" />
            <p className="text-slate-600">Loading market data...</p>
          </div>
        ) : error ? (
          <div className="p-12 text-center text-red-600">
            Failed to load data. Try refreshing.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b border-slate-200">
                {table.getHeaderGroups().map(headerGroup => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map(header => (
                      <th
                        key={header.id}
                        className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 select-none"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        <div className="flex items-center space-x-1">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getIsSorted() === 'asc' ? (
                            <ChevronUp className="h-4 w-4" />
                          ) : header.column.getIsSorted() === 'desc' ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronsUpDown className="h-4 w-4 opacity-30" />
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-slate-200">
                {table.getRowModel().rows.map(row => (
                  <tr
                    key={row.id}
                    onClick={() => handleRowClick(row.original)}
                    className="hover:bg-blue-50 cursor-pointer transition-colors"
                  >
                    {row.getVisibleCells().map(cell => (
                      <td key={cell.id} className="px-4 py-3 whitespace-nowrap text-sm text-slate-900">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="p-4 border-t border-slate-200 flex items-center justify-between">
          <button
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            className="px-3 py-1 text-sm bg-white border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-sm text-slate-600">
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <button
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            className="px-3 py-1 text-sm bg-white border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>

      {/* Stock Details */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Stock Details</h2>
        
        <div className="flex space-x-2 mb-6">
          <input
            type="text"
            value={searchTicker}
            onChange={(e) => setSearchTicker(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search any ticker (e.g. NVDA, TSLA)"
            className="flex-1 px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            onClick={handleSearch}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center"
          >
            <Search className="h-4 w-4 mr-2" />
            Search
          </button>
        </div>

        {selectedStock && stockDetails ? (
          <div>
            {!stockDetails.found ? (
              <div className="text-center py-8 text-amber-600 bg-amber-50 rounded-lg">
                No data found for '{selectedStock}'. Check the ticker and try again.
              </div>
            ) : (
              <div className="space-y-6">
                <div>
                  <h3 className="text-xl font-bold text-slate-900">
                    {stockDetails.name} ({stockDetails.symbol})
                  </h3>
                  {stockDetails.summary && (
                    <details className="mt-3">
                      <summary className="cursor-pointer text-sm font-medium text-blue-600 hover:text-blue-700">
                        Business Summary
                      </summary>
                      <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                        {stockDetails.summary}
                      </p>
                    </details>
                  )}
                </div>

                {/* Price Chart */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="font-semibold text-slate-900">Price History</h4>
                    <div className="flex space-x-1">
                      {rangesData?.ranges?.map((range: string) => (
                        <button
                          key={range}
                          onClick={() => setPriceRange(range)}
                          className={`px-3 py-1 text-xs rounded-md transition-colors ${
                            priceRange === range
                              ? 'bg-blue-600 text-white'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          }`}
                        >
                          {range}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={priceHistory}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis 
                          dataKey="time" 
                          tick={{ fontSize: 12 }}
                          tickFormatter={(value) => {
                            const date = new Date(value)
                            return date.toLocaleDateString()
                          }}
                        />
                        <YAxis 
                          tick={{ fontSize: 12 }}
                          tickFormatter={(value) => `$${value.toFixed(0)}`}
                        />
                        <Tooltip 
                          formatter={(value: any) => [`$${Number(value).toFixed(2)}`, 'Price']}
                          labelFormatter={(label) => new Date(label).toLocaleDateString()}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="price" 
                          stroke="#2563eb" 
                          strokeWidth={2}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Details Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {stockDetails.sections.map(([title, rows], idx) => (
                    <div key={idx}>
                      <h4 className="font-semibold text-slate-900 mb-3 pb-2 border-b border-slate-200">
                        {title}
                      </h4>
                      <div className="space-y-2">
                        {rows.map(([label, value, kind], rowIdx) => (
                          <div key={rowIdx} className="flex justify-between py-1.5">
                            <span className="text-sm text-slate-600">{label}</span>
                            <span className="text-sm font-medium text-slate-900">
                              {formatValue(value, kind)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-12 text-slate-500 bg-slate-50 rounded-lg">
            Click any row above or search a ticker to see details
          </div>
        )}
      </div>
    </div>
  )
}
