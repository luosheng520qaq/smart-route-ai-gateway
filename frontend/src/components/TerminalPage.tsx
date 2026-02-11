
import { useEffect, useRef, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import 'xterm/css/xterm.css';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Download, Eraser, Pause, Play, Wifi, WifiOff, Terminal as TerminalIcon } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export function TerminalPage() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [filter, setFilter] = useState("");
  const bufferRef = useRef<string[]>([]);
  const MAX_BUFFER = 10000;

  useEffect(() => {
    // Initialize XTerm
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      lineHeight: 1.5,
      fontFamily: 'JetBrains Mono, Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#1e293b', // Slate-800 (Blue-ish dark, not pure black)
        foreground: '#e2e8f0', // Slate-200
        selectionBackground: '#475569', // Slate-600
        cursor: '#94a3b8', // Slate-400
        
        // ANSI Colors (One Dark / Dracula inspired)
        black: '#1e293b',
        red: '#ff5c57',
        green: '#5af78e',
        yellow: '#f3f99d',
        blue: '#57c7ff',
        magenta: '#ff6ac1',
        cyan: '#9aedfe',
        white: '#f1f5f9',
        brightBlack: '#686868',
        brightRed: '#ff5c57',
        brightGreen: '#5af78e',
        brightYellow: '#f3f99d',
        brightBlue: '#57c7ff',
        brightMagenta: '#ff6ac1',
        brightCyan: '#9aedfe',
        brightWhite: '#f8fafc',
      },
      convertEol: true,
      disableStdin: true, // Read-only
      scrollback: 10000,
      allowProposedApi: true,
      // Allow selection
      rightClickSelectsWord: true,
    });
    
    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();
    
    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);
    
    if (terminalRef.current) {
      term.open(terminalRef.current);
      fitAddon.fit();
    }
    
    xtermRef.current = term;
    fitAddonRef.current = fitAddon;

    // Handle resize with ResizeObserver
    const resizeObserver = new ResizeObserver(() => {
        // Debounce slightly to avoid flicker
        requestAnimationFrame(() => fitAddon.fit());
    });
    
    if (terminalRef.current) {
        resizeObserver.observe(terminalRef.current);
    }

    // Connect WS
    connectWebSocket();

    return () => {
      resizeObserver.disconnect();
      wsRef.current?.close();
      term.dispose();
    };
  }, []);

  const connectWebSocket = () => {
    // Use relative path or env
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.NODE_ENV === 'development' ? 'localhost:6688' : window.location.host;
    const wsUrl = `${protocol}//${host}/ws/logs`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      setIsConnected(true);
      xtermRef.current?.writeln('\x1b[32m✓ [System] 已连接到日志流\x1b[0m');
    };
    
    ws.onclose = () => {
      setIsConnected(false);
      xtermRef.current?.writeln('\x1b[31m✗ [System] 连接断开，3秒后重连...\x1b[0m');
      setTimeout(connectWebSocket, 3000);
    };
    
    ws.onmessage = (event) => {
      if (isPaused) return;
      
      const msg = event.data;
      
      // Filter logic (simple string match)
      if (filter && !msg.toLowerCase().includes(filter.toLowerCase())) {
        return;
      }

      // Add to buffer
      bufferRef.current.push(msg);
      if (bufferRef.current.length > MAX_BUFFER) {
        bufferRef.current.shift();
      }

      // Format message for CMD-like appearance
      let displayMsg = msg;
      
      // Check for separator (starts with at least 5 dashes or equals)
      const isSeparator = /^[=-]{5,}/.test(msg.trim());

      if (isSeparator) {
           // Make separator bold and bright blue for visibility
           displayMsg = `\x1b[1;94m${msg}\x1b[0m`;
      } else if (!msg.startsWith('[')) {
          const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
          displayMsg = `[${timestamp}] ${msg}`;
      }

      // --- Enhanced Coloring ---
      
      if (!isSeparator) {
        // 1. Time: [HH:MM:SS] -> Gray
        displayMsg = displayMsg.replace(/^(\[\d{2}:\d{2}:\d{2}(\.\d+)?\])/, '\x1b[90m$1\x1b[0m');
  
        // 2. Stage: 【Stage】 -> Cyan/Blue
        // Need to handle regex carefully to avoid matching too much
        displayMsg = displayMsg.replace(/【(.*?)】/g, '\x1b[36m【$1】\x1b[0m');
  
        // 3. Status: 成功 -> Green, 失败/错误 -> Red, Warning -> Yellow
        displayMsg = displayMsg.replace(/(成功|success)/gi, '\x1b[32m$1\x1b[0m');
        displayMsg = displayMsg.replace(/(失败|fail|error|exception)/gi, '\x1b[31m$1\x1b[0m');
        displayMsg = displayMsg.replace(/(警告|warning|retry)/gi, '\x1b[33m$1\x1b[0m');
        
        // 4. Details/Meta
        // (耗时: 123ms) -> Magenta
        displayMsg = displayMsg.replace(/(\(耗时: .*?\))/g, '\x1b[35m$1\x1b[0m');
        
        // [重试: N] -> Yellow
        displayMsg = displayMsg.replace(/(\[重试: \d+\])/g, '\x1b[33m$1\x1b[0m');
        
        // Trace ID <abc> -> Dim
        displayMsg = displayMsg.replace(/(<[a-f0-9-]{8}>)$/i, '\x1b[2m$1\x1b[0m');
  
        // Special handling for [System]
        if (displayMsg.includes('[System]')) {
           displayMsg = displayMsg.replace('[System]', '\x1b[1;36m[System]\x1b[0m');
        }
      }

      xtermRef.current?.writeln(displayMsg);
    };
    
    wsRef.current = ws;
  };

  const handleClear = () => {
    xtermRef.current?.clear();
    bufferRef.current = [];
  };

  const handleExport = () => {
    const content = bufferRef.current.join('\n');
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

  return (
    <div className="h-[calc(100vh-6rem)] animate-in fade-in duration-500">
      <Card className="h-full flex flex-col shadow-sm border-zinc-200 dark:border-zinc-800 hover:!translate-y-0 hover:!shadow-sm transition-none">
        <CardHeader className="flex flex-row items-center justify-between py-3 px-4 space-y-0 border-b">
          <div className="flex items-center gap-3">
             <div className="p-2 bg-primary/10 rounded-lg">
                <TerminalIcon className="h-5 w-5 text-primary" />
             </div>
             <div>
                <CardTitle className="text-lg font-semibold">实时终端</CardTitle>
                <div className="flex items-center gap-2 mt-1">
                    <Badge variant={isConnected ? "default" : "destructive"} className="h-5 px-1.5 text-[10px] gap-1 font-normal">
                        {isConnected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
                        {isConnected ? '已连接' : '断开连接'}
                    </Badge>
                    <span className="text-xs text-muted-foreground hidden sm:inline-block">
                        ws://{process.env.NODE_ENV === 'development' ? 'localhost:6688' : window.location.host}/ws/logs
                    </span>
                </div>
             </div>
          </div>
          
          <div className="flex items-center gap-2">
            <div className="relative hidden sm:block">
                <Input 
                  className="w-48 h-8 text-xs font-mono bg-muted/50" 
                  placeholder="grep ..." 
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
                            className={`h-8 w-8 p-0 ${isPaused ? 'bg-yellow-100 dark:bg-yellow-900/20 text-yellow-600' : ''}`}
                            onClick={() => setIsPaused(!isPaused)}
                        >
                            {isPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>{isPaused ? "继续滚动" : "暂停滚动"}</p>
                    </TooltipContent>
                </Tooltip>

                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={handleClear}>
                            <Eraser className="h-4 w-4" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>清空屏幕</p>
                    </TooltipContent>
                </Tooltip>

                <Tooltip>
                    <TooltipTrigger asChild>
                         <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={handleExport}>
                            <Download className="h-4 w-4" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>导出日志</p>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>
          </div>
        </CardHeader>
        
        <CardContent className="flex-1 p-0 relative min-h-0 bg-[#1e293b] select-text">
           <div ref={terminalRef} className="absolute inset-0 p-4 overflow-hidden" />
        </CardContent>
      </Card>
    </div>
  );
}
