import { useState } from 'react'
import { Dashboard } from '@/components/Dashboard'
import { ConfigPage } from '@/components/ConfigPage'
import { LogsPage } from '@/components/LogsPage'
import { Toaster } from "@/components/ui/sonner"
import { LayoutDashboard, Settings, Boxes, ScrollText, Menu } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"

interface SidebarProps {
  activeTab: 'dashboard' | 'config' | 'logs';
  setActiveTab: (tab: 'dashboard' | 'config' | 'logs') => void;
  closeSheet?: () => void;
}

function SidebarContent({ activeTab, setActiveTab, closeSheet }: SidebarProps) {
  const handleTabClick = (tab: 'dashboard' | 'config' | 'logs') => {
    setActiveTab(tab);
    if (closeSheet) closeSheet();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 flex items-center gap-4 border-b border-white/20">
        <div className="p-3 bg-gradient-to-tr from-sky-400 to-cyan-300 rounded-xl shadow-lg shadow-sky-500/20 animate-pulse-slow">
          <Boxes className="h-6 w-6 text-white" />
        </div>
        <h1 className="font-bold text-xl bg-clip-text text-transparent bg-gradient-to-r from-sky-600 to-cyan-500">智能路由</h1>
      </div>
      <nav className="flex-1 p-4 space-y-3">
        <button
          onClick={() => handleTabClick('dashboard')}
          className={cn(
            "w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-base font-medium transition-all duration-300 group relative overflow-hidden",
            activeTab === 'dashboard'
              ? "bg-white/60 text-primary shadow-lg shadow-sky-500/10 backdrop-blur-md"
              : "hover:bg-white/30 text-slate-500 hover:text-primary hover:shadow-md"
          )}
        >
          {activeTab === 'dashboard' && <div className="absolute left-0 top-0 h-full w-1.5 bg-sky-500 rounded-r-full" />}
          <LayoutDashboard className={cn("h-5 w-5 transition-transform duration-300", activeTab === 'dashboard' ? "scale-110" : "group-hover:scale-110")} />
          仪表盘
        </button>
        <button
          onClick={() => handleTabClick('logs')}
          className={cn(
            "w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-base font-medium transition-all duration-300 group relative overflow-hidden",
            activeTab === 'logs'
              ? "bg-white/60 text-primary shadow-lg shadow-sky-500/10 backdrop-blur-md"
              : "hover:bg-white/30 text-slate-500 hover:text-primary hover:shadow-md"
          )}
        >
          {activeTab === 'logs' && <div className="absolute left-0 top-0 h-full w-1.5 bg-sky-500 rounded-r-full" />}
          <ScrollText className={cn("h-5 w-5 transition-transform duration-300", activeTab === 'logs' ? "scale-110" : "group-hover:scale-110")} />
          日志
        </button>
        <button
          onClick={() => handleTabClick('config')}
          className={cn(
            "w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-base font-medium transition-all duration-300 group relative overflow-hidden",
            activeTab === 'config'
              ? "bg-white/60 text-primary shadow-lg shadow-sky-500/10 backdrop-blur-md"
              : "hover:bg-white/30 text-slate-500 hover:text-primary hover:shadow-md"
          )}
        >
          {activeTab === 'config' && <div className="absolute left-0 top-0 h-full w-1.5 bg-sky-500 rounded-r-full" />}
          <Settings className={cn("h-5 w-5 transition-transform duration-300", activeTab === 'config' ? "scale-110" : "group-hover:scale-110")} />
          系统配置
        </button>
      </nav>
      <div className="p-6 border-t border-white/20">
        <div className="text-xs text-slate-400 font-medium text-center glass py-3 px-4 rounded-xl shadow-sm">
          v1.1.0
        </div>
      </div>
    </div>
  );
}


function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'config' | 'logs'>('dashboard')
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col md:flex-row font-sans selection:bg-primary/20 relative overflow-hidden">
      {/* Liquid Background */}
      <div className="liquid-bg">
        <div className="liquid-blob blob-1"></div>
        <div className="liquid-blob blob-2"></div>
        <div className="liquid-blob blob-3"></div>
      </div>

      {/* Mobile Header */}
      <div className="md:hidden p-4 flex items-center justify-between glass sticky top-0 z-20 border-b border-white/40">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-tr from-sky-400 to-cyan-300 rounded-xl shadow-lg shadow-sky-500/20">
            <Boxes className="h-5 w-5 text-white" />
          </div>
          <h1 className="font-bold text-lg bg-clip-text text-transparent bg-gradient-to-r from-sky-600 to-cyan-500">智能路由</h1>
        </div>
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger asChild>
            <button className="p-2 hover:bg-white/50 rounded-xl transition-all active:scale-95">
              <Menu className="h-6 w-6 text-slate-500" />
            </button>
          </SheetTrigger>
          <SheetContent side="left" className="p-0 w-72 border-r border-white/20 bg-white/40 backdrop-blur-3xl">
             <SidebarContent activeTab={activeTab} setActiveTab={setActiveTab} closeSheet={() => setSheetOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>

      {/* Desktop Sidebar */}
      <div className="hidden md:flex w-64 sidebar-glass flex-col fixed h-full z-10 transition-all duration-300">
        <SidebarContent activeTab={activeTab} setActiveTab={setActiveTab} />
      </div>

      {/* Main Content */}
      <main className="flex-1 md:pl-64 overflow-y-auto min-h-screen relative z-0">
        <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8">
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
