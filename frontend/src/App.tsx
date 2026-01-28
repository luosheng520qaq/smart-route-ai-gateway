import { useState } from 'react'
import { Dashboard } from '@/components/Dashboard'
import { ConfigPage } from '@/components/ConfigPage'
import { LogsPage } from '@/components/LogsPage'
import { Toaster } from "@/components/ui/sonner"
import { LayoutDashboard, Settings, Boxes, ScrollText } from 'lucide-react'
import { cn } from '@/lib/utils'

function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'config' | 'logs'>('dashboard')

  return (
    <div className="min-h-screen flex font-sans selection:bg-primary/20">
      {/* Sidebar */}
      <div className="w-64 sidebar-glass flex flex-col fixed h-full z-10 transition-all duration-300">
        <div className="p-6 flex items-center gap-3 border-b border-white/20">
          <div className="p-2 bg-gradient-to-tr from-primary to-purple-500 rounded-lg shadow-lg">
            <Boxes className="h-5 w-5 text-white" />
          </div>
          <h1 className="font-bold text-lg bg-clip-text text-transparent bg-gradient-to-r from-slate-800 to-slate-600">智能路由</h1>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={cn(
              "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
              activeTab === 'dashboard' 
                ? "bg-white/80 shadow-md text-primary scale-[1.02]" 
                : "hover:bg-white/40 text-slate-600 hover:text-slate-900"
            )}
          >
            <LayoutDashboard className="h-4 w-4" />
            仪表盘
          </button>
           <button
            onClick={() => setActiveTab('logs')}
            className={cn(
              "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
              activeTab === 'logs' 
                ? "bg-white/80 shadow-md text-primary scale-[1.02]" 
                : "hover:bg-white/40 text-slate-600 hover:text-slate-900"
            )}
          >
            <ScrollText className="h-4 w-4" />
            日志
          </button>
          <button
            onClick={() => setActiveTab('config')}
            className={cn(
              "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
              activeTab === 'config' 
                ? "bg-white/80 shadow-md text-primary scale-[1.02]" 
                : "hover:bg-white/40 text-slate-600 hover:text-slate-900"
            )}
          >
            <Settings className="h-4 w-4" />
            系统配置
          </button>
        </nav>
        <div className="p-6 border-t border-white/20">
          <div className="text-xs text-slate-500 font-medium text-center glass py-2 px-4 rounded-full">
            v1.1.0
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 pl-64 overflow-y-auto min-h-screen">
        <div className="p-8 max-w-7xl mx-auto">
          {activeTab === 'dashboard' && <Dashboard />}
          {activeTab === 'logs' && <LogsPage />}
          {activeTab === 'config' && <ConfigPage />}
        </div>
      </main>

      <Toaster />
    </div>
  )
}

export default App
