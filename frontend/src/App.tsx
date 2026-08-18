import { Routes, Route, NavLink } from 'react-router-dom'
import MarketRankingPage from './pages/MarketRankingPage'
import PortfolioPage from './pages/PortfolioPage'
import AIAssistantPage from './pages/AIAssistantPage'
import { BarChart3, Briefcase, Bot } from 'lucide-react'

function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <BarChart3 className="h-8 w-8 text-blue-600 mr-3" />
              <h1 className="text-xl font-bold text-slate-900">Market Analyzer</h1>
            </div>
            <nav className="flex space-x-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`
                }
              >
                <BarChart3 className="h-4 w-4 mr-2" />
                Market Ranking
              </NavLink>
              <NavLink
                to="/portfolio"
                className={({ isActive }) =>
                  `flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`
                }
              >
                <Briefcase className="h-4 w-4 mr-2" />
                Portfolio
              </NavLink>
              <NavLink
                to="/ai"
                className={({ isActive }) =>
                  `flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`
                }
              >
                <Bot className="h-4 w-4 mr-2" />
                AI Assistant
              </NavLink>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<MarketRankingPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/ai" element={<AIAssistantPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
