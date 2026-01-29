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
      <div className="p-6 flex items-center gap-3 border-b border-white/20">
        <div className="p-2 bg-gradient-to-tr from-primary to-purple-500 rounded-lg shadow-lg">
          <Boxes className="h-5 w-5 text-white" />
        </div>
        <h1 className="font-bold text-lg bg-clip-text text-transparent bg-gradient-to-r from-slate-800 to-slate-600">智能路由</h1>
      </div>
      <nav className="flex-1 p-4 space-y-2">
        <button
          onClick={() => handleTabClick('dashboard')}
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
          onClick={() => handleTabClick('logs')}
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
          onClick={() => handleTabClick('config')}
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
  );
}

function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'config' | 'logs'>('dashboard')
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col md:flex-row font-sans selection:bg-primary/20">
      {/* Mobile Header */}
      <div className="md:hidden p-4 flex items-center justify-between glass sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="p-1.5 bg-gradient-to-tr from-primary to-purple-500 rounded-lg shadow-lg">
            <Boxes className="h-4 w-4 text-white" />
          </div>
          <h1 className="font-bold text-base bg-clip-text text-transparent bg-gradient-to-r from-slate-800 to-slate-600">智能路由</h1>
        </div>
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger asChild>
            <button className="p-2 hover:bg-white/50 rounded-lg transition-colors">
              <Menu className="h-5 w-5 text-slate-600" />
            </button>
          </SheetTrigger>
          <SheetContent side="left" className="p-0 w-72 border-r border-white/20 bg-white/60 backdrop-blur-xl">
             <SidebarContent activeTab={activeTab} setActiveTab={setActiveTab} closeSheet={() => setSheetOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>

      {/* Desktop Sidebar */}
      <div className="hidden md:flex w-64 sidebar-glass flex-col fixed h-full z-10 transition-all duration-300">
        <SidebarContent activeTab={activeTab} setActiveTab={setActiveTab} />
      </div>

      {/* Main Content */}
      <main className="flex-1 md:pl-64 overflow-y-auto min-h-screen">
        <div className="p-4 md:p-8 max-w-7xl mx-auto">
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
