
import { useEffect, useRef, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import 'xterm/css/xterm.css';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Download, Eraser, Pause, Play } from 'lucide-react';
import { toast } from 'sonner';

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
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#1e1e1e',
        foreground: '#d4d4d4',
      },
      convertEol: true,
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

    // Handle resize
    const handleResize = () => fitAddon.fit();
    window.addEventListener('resize', handleResize);

    // Connect WS
    connectWebSocket();

    return () => {
      window.removeEventListener('resize', handleResize);
      wsRef.current?.close();
      term.dispose();
    };
  }, []);

  const connectWebSocket = () => {
    // Use relative path or env
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Assuming backend is on same host/port if served via fallback, otherwise adjust
    // For dev (Vite default 5173, Backend 6688), we need hardcoded or env
    // But api.ts uses relative path for API_BASE_URL which is empty string.
    // So we assume proxy or same origin. 
    // If dev mode: 
    const host = process.env.NODE_ENV === 'development' ? 'localhost:6688' : window.location.host;
    const wsUrl = `${protocol}//${host}/ws/logs`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      setIsConnected(true);
      xtermRef.current?.writeln('\x1b[32m[System] Connected to log stream\x1b[0m');
    };
    
    ws.onclose = () => {
      setIsConnected(false);
      xtermRef.current?.writeln('\x1b[31m[System] Disconnected. Reconnecting in 3s...\x1b[0m');
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
      // Add timestamp if missing
      let displayMsg = msg;
      if (!msg.startsWith('[')) {
          const timestamp = new Date().toLocaleTimeString();
          displayMsg = `[${timestamp}] ${msg}`;
      }

      // Enhanced Colorizing for CMD style
      // Green for success/info, Red for errors, Yellow for warnings/retries, Cyan for system info
      if (displayMsg.includes('| success')) {
        displayMsg = displayMsg.replace('| success', '|\x1b[32m success \x1b[0m');
      } else if (displayMsg.includes('| fail') || displayMsg.includes('error') || displayMsg.includes('Error') || displayMsg.includes('Exception')) {
        displayMsg = displayMsg.replace(/(\| fail|error|Error|Exception)/g, (match: string) => `\x1b[31m${match}\x1b[0m`);
      } else if (displayMsg.includes('| retry') || displayMsg.includes('warning') || displayMsg.includes('Warning')) {
         displayMsg = displayMsg.replace(/(\| retry|warning|Warning)/g, (match: string) => `\x1b[33m${match}\x1b[0m`);
      } else if (displayMsg.includes('[System]')) {
         displayMsg = displayMsg.replace('[System]', '\x1b[36m[System]\x1b[0m');
      }
      
      // Highlight specific keywords like REQ_RECEIVED, MODEL_CALL_START etc
      const keywords = ["REQ_RECEIVED", "ROUTER_START", "ROUTER_END", "MODEL_CALL_START", "FIRST_TOKEN", "FULL_RESPONSE", "ALL_FAILED"];
      keywords.forEach(k => {
          if (displayMsg.includes(k)) {
              displayMsg = displayMsg.replace(k, `\x1b[1;36m${k}\x1b[0m`);
          }
      });

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
    a.download = `smart-route-logs-${new Date().toISOString()}.log`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("日志已导出");
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">实时终端</h2>
          <p className="text-muted-foreground flex items-center gap-2">
            Status: 
            <span className={`inline-block w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            {isConnected ? 'Connected' : 'Disconnected'}
          </p>
        </div>
        <div className="flex gap-2">
          <Input 
            className="w-48" 
            placeholder="Filter logs..." 
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <Button variant="outline" size="icon" onClick={() => setIsPaused(!isPaused)}>
            {isPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
          </Button>
          <Button variant="outline" size="icon" onClick={handleClear}>
            <Eraser className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" onClick={handleExport}>
            <Download className="h-4 w-4" />
          </Button>
        </div>
      </div>
      
      <div className="flex-1 min-h-[500px] border rounded-lg overflow-hidden bg-[#1e1e1e] p-2 relative">
         <div ref={terminalRef} className="h-full w-full" />
      </div>
    </div>
  );
}
