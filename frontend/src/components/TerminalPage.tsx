import { useEffect, useRef, useState } from 'react';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Download, Eraser, Pause, Play, Wifi, WifiOff, Terminal as TerminalIcon, ChevronDown, Search } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from '@/lib/utils';

interface LogEntry {
  id: number;
  time: string;
  message: string;
  level: 'info' | 'success' | 'error' | 'warning' | 'system';
  raw: string;
}

export function TerminalPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [filter, setFilter] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [showNewIndicator, setShowNewIndicator] = useState(false);
  const [isUserScrolling, setIsUserScrolling] = useState(false);
  const logIdRef = useRef(0);
  const logsRef = useRef<LogEntry[]>([]);
  const filterRef = useRef(filter);
  const MAX_LOGS = 500;

  useEffect(() => {
    filterRef.current = filter;
  }, [filter]);

  const parseLogLevel = (msg: string): LogEntry['level'] => {
    if (msg.includes('error') || msg.includes('失败') || msg.includes('exception')) return 'error';
    if (msg.includes('success') || msg.includes('成功') || msg.includes('✓')) return 'success';
    if (msg.includes('warning') || msg.includes('警告') || msg.includes('retry')) return 'warning';
    if (msg.includes('[System]')) return 'system';
    return 'info';
  };

  const formatTime = () => {
    const now = new Date();
    return now.toLocaleTimeString('zh-CN', { hour12: false });
  };

  const isPausedRef = useRef(isPaused);
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  const isUserScrollingRef = useRef(isUserScrolling);
  useEffect(() => {
    isUserScrollingRef.current = isUserScrolling;
  }, [isUserScrolling]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.NODE_ENV === 'development' ? 'localhost:6688' : window.location.host;
    const wsUrl = `${protocol}//${host}/ws/logs`;

    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        const entry: LogEntry = {
          id: logIdRef.current++,
          time: formatTime(),
          message: '✓ [System] 已连接到日志流',
          level: 'system',
          raw: '[System] 已连接到日志流'
        };
        logsRef.current.push(entry);
        if (logsRef.current.length > MAX_LOGS) {
          logsRef.current = logsRef.current.slice(-MAX_LOGS);
        }
        setLogs([...logsRef.current]);
      };

      ws.onclose = () => {
        setIsConnected(false);
        const entry: LogEntry = {
          id: logIdRef.current++,
          time: formatTime(),
          message: '✗ [System] 连接断开，3秒后重连...',
          level: 'warning',
          raw: '[System] 连接断开'
        };
        logsRef.current.push(entry);
        if (logsRef.current.length > MAX_LOGS) {
          logsRef.current = logsRef.current.slice(-MAX_LOGS);
        }
        setLogs([...logsRef.current]);
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws?.close();
      };

      ws.onmessage = (event) => {
        const msg = event.data;
        
        if (filterRef.current && !msg.toLowerCase().includes(filterRef.current.toLowerCase())) {
          return;
        }

        const level = parseLogLevel(msg);
        const time = formatTime();

        const entry: LogEntry = {
          id: logIdRef.current++,
          time,
          message: msg,
          level,
          raw: msg,
        };

        logsRef.current.push(entry);
        if (logsRef.current.length > MAX_LOGS) {
          logsRef.current = logsRef.current.slice(-MAX_LOGS);
        }
        
        if (!isPausedRef.current) {
          setLogs([...logsRef.current]);
          if (!isUserScrollingRef.current && containerRef.current) {
            requestAnimationFrame(() => {
              containerRef.current?.scrollTo({
                top: containerRef.current.scrollHeight,
                behavior: 'auto'
              });
            });
          } else if (isUserScrollingRef.current) {
            setShowNewIndicator(true);
          }
        }
      };
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    const handleScroll = () => {
      if (!containerRef.current) return;
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      setIsUserScrolling(!isAtBottom);
      if (isAtBottom) {
        setShowNewIndicator(false);
      }
    };

    const container = containerRef.current;
    container?.addEventListener('scroll', handleScroll, { passive: true });
    return () => container?.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToBottom = () => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth'
      });
      setShowNewIndicator(false);
      setIsUserScrolling(false);
    }
  };

  const handleClear = () => {
    logsRef.current = [];
    setLogs([]);
    setShowNewIndicator(false);
  };

  const handleExport = () => {
    const content = logsRef.current.map(l => l.raw).join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `smart-route-logs-${new Date().toISOString().replace(/[:.]/g, '-')}.log`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("日志已导出");
  };

  const getLevelColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'error': return 'text-red-400 bg-red-400/10 border-red-400/20';
      case 'success': return 'text-green-400 bg-green-400/10 border-green-400/20';
      case 'warning': return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20';
      case 'system': return 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20';
      default: return 'text-zinc-300 bg-zinc-800/50 border-zinc-700/30';
    }
  };

  const filteredLogs = filter ? logs.filter(l => 
    l.raw.toLowerCase().includes(filter.toLowerCase())
  ) : logs;

  return (
    <div className="h-[calc(100vh-6rem)] animate-in fade-in duration-500 flex flex-col">
      <Card className="h-full flex flex-col shadow-sm border-zinc-200 dark:border-zinc-800">
        <CardHeader className="flex flex-row items-center justify-between py-3 px-4 space-y-0 border-b shrink-0">
          <div className="flex items-center gap-3">
             <div className="p-2 bg-primary/10 rounded-lg">
                <TerminalIcon className="h-5 w-5 text-primary" />
             </div>
             <div>
                <CardTitle className="text-lg font-semibold">实时终端</CardTitle>
                <div className="flex items-center gap-2 mt-1">
                    <Badge variant={isConnected ? "default" : "destructive"} className="h-5 px-1.5 text-[10px] gap-1 font-normal">
                        {isConnected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
                        {isConnected ? '已连接' : '断开'}
                    </Badge>
                    <span className="text-xs text-muted-foreground hidden sm:inline-block">
                        {logs.length} 条日志
                    </span>
                </div>
             </div>
          </div>
          
          <div className="flex items-center gap-2">
            <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input 
                  className="w-36 h-8 pl-8 text-xs bg-muted/50" 
                  placeholder="筛选..." 
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
            </div>
            
            <TooltipProvider>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button 
                            variant="outline" 
                            size="sm" 
                            className={cn(
                              "h-8 w-8 p-0",
                              isPaused && "bg-yellow-100 dark:bg-yellow-900/20 text-yellow-600 border-yellow-400"
                            )}
                            onClick={() => setIsPaused(!isPaused)}
                        >
                            {isPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>{isPaused ? "继续" : "暂停"}</p>
                    </TooltipContent>
                </Tooltip>

                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={handleClear}>
                            <Eraser className="h-4 w-4" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>清空</p>
                    </TooltipContent>
                </Tooltip>

                <Tooltip>
                    <TooltipTrigger asChild>
                         <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={handleExport}>
                            <Download className="h-4 w-4" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>导出</p>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>
          </div>
        </CardHeader>
        
        <CardContent className="flex-1 p-0 relative min-h-0 overflow-hidden bg-[#0d1117]">
           <div 
             ref={containerRef}
             className="absolute inset-0 overflow-y-auto overflow-x-hidden px-3 py-2 scroll-smooth"
             style={{
               scrollbarWidth: 'thin',
               scrollbarColor: '#3f3f46 #1a1a1a',
             }}
           >
             <div className="space-y-0.5">
               {filteredLogs.map((log) => (
                 <div 
                   key={log.id}
                   className={cn(
                     "flex gap-2 py-0.5 px-1.5 rounded text-[11px] leading-relaxed font-mono border border-transparent",
                     getLevelColor(log.level)
                   )}
                 >
                   <span className="text-zinc-500 shrink-0 tabular-nums">[{log.time}]</span>
                   <span className="whitespace-pre-wrap break-all flex-1">{log.message}</span>
                 </div>
               ))}
               
               {filteredLogs.length === 0 && (
                 <div className="text-center py-8 text-zinc-500 text-sm">
                   {isConnected ? '等待日志...' : '连接中...'}
                 </div>
               )}
             </div>
           </div>

           {showNewIndicator && !isPaused && (
             <button
               onClick={scrollToBottom}
               className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground px-3 py-1.5 rounded-full text-xs font-medium shadow-lg flex items-center gap-1.5 animate-bounce hover:bg-primary/90 transition-colors"
             >
               <ChevronDown className="h-3 w-3" />
               新日志
             </button>
           )}
        </CardContent>
      </Card>
    </div>
  );
}
