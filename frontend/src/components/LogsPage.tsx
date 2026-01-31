import { useEffect, useState } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { CalendarIcon } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { CheckCircle2, XCircle, RefreshCw, FileText, Download, Lock } from 'lucide-react';
import { fetchLogs, exportLogs, RequestLog, TraceEvent, LogFilters } from '@/lib/api';

export function LogsPage() {
  const [logs, setLogs] = useState<RequestLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [authError, setAuthError] = useState(false);
  const [apiKey, setApiKey] = useState("");
  
  // Filters
  const [filters, setFilters] = useState<LogFilters>({
    level: 'all',
    status: 'all',
    model: '',
    start_date: '',
    end_date: ''
  });
  
  // Date State Helper
  const [startDate, setStartDate] = useState<Date | undefined>();
  const [endDate, setEndDate] = useState<Date | undefined>();

  // Sync Date State to Filters
  useEffect(() => {
      if (startDate) {
          setFilters(prev => ({ ...prev, start_date: startDate.toISOString() }));
      } else {
          setFilters(prev => ({ ...prev, start_date: '' }));
      }
  }, [startDate]);

  useEffect(() => {
      if (endDate) {
          setFilters(prev => ({ ...prev, end_date: endDate.toISOString() }));
      } else {
          setFilters(prev => ({ ...prev, end_date: '' }));
      }
  }, [endDate]);

  const pageSize = 50;

  const loadData = async () => {
    setLoading(true);
    setAuthError(false);
    try {
      const logsData = await fetchLogs(page, pageSize, filters);
      setLogs(logsData.logs);
      setTotal(logsData.total);
    } catch (error: any) {
      console.error("Failed to load logs", error);
      if (error.response?.status === 401) {
          setAuthError(true);
          setAutoRefresh(false); // Stop refreshing on auth error
      }
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    try {
        const blob = await exportLogs(filters);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `logs_export_${new Date().toISOString()}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (e) {
        console.error("Export failed", e);
    }
  };

  const saveApiKey = () => {
      localStorage.setItem('gateway_key', apiKey);
      setAuthError(false);
      loadData();
  };

  useEffect(() => {
    loadData();
  }, [page, filters]); // Reload when page or filters change

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (autoRefresh && !authError) {
      interval = setInterval(() => {
        // Only refresh if on first page to avoid jumping
        if (page === 1) {
            fetchLogs(1, pageSize, filters).then(data => {
                setLogs(data.logs);
                setTotal(data.total);
            }).catch(e => {
                if (e.response?.status === 401) {
                    setAuthError(true);
                    setAutoRefresh(false);
                }
            });
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [autoRefresh, page, filters, authError]);

  const renderMessageContent = (jsonStr: string, isResponse: boolean) => {
      try {
          const data = JSON.parse(jsonStr);
          
          // Request Logic (Array of messages)
          if (Array.isArray(data)) {
              return (
                  <div className="space-y-4">
                      {data.map((msg, idx) => {
                          if (msg.role === 'tool') {
                              let formattedContent = msg.content;
                              let toolName = (msg as any).name || (msg as any).tool_call_id;
                              
                              try {
                                  if (typeof msg.content === 'string') {
                                      formattedContent = JSON.stringify(JSON.parse(msg.content), null, 2);
                                  }
                              } catch (e) {}

                              return (
                                  <div key={idx} className="bg-muted p-3 rounded-md text-sm">
                                      <div className="font-semibold mb-1 text-xs text-muted-foreground uppercase flex justify-between items-center">
                                          <span>【工具返回】</span>
                                          {toolName && <span className="font-mono text-[10px] opacity-70">{toolName}</span>}
                                      </div>
                                      
                                      <div className="mt-2 pl-2 border-l-2 border-blue-500/50">
                                          <div className="text-xs font-medium mb-1 text-blue-600">🔙 执行结果:</div>
                                          <div className="font-mono text-xs bg-background p-2 rounded border overflow-auto max-h-[300px]">
                                              <div className="text-foreground break-all whitespace-pre-wrap">
                                                  {typeof formattedContent === 'string' ? formattedContent : JSON.stringify(formattedContent, null, 2)}
                                              </div>
                                          </div>
                                      </div>
                                  </div>
                              );
                          }

                          // Try to parse tool output if it's JSON
                          let contentDisplay = msg.content;
                          if (msg.role === 'tool' && typeof msg.content === 'string') {
                              try {
                                  // Skip if we already handled it above
                              } catch (e) {
                                  // Not JSON, keep as is
                              }
                          }

                          return (
                              <div key={idx} className="bg-muted p-3 rounded-md text-sm">
                                  <div className="font-semibold mb-1 text-xs text-muted-foreground uppercase">
                                      【{msg.role === 'user' ? '用户' : msg.role === 'system' ? '系统' : msg.role === 'assistant' ? '助手' : msg.role === 'tool' ? '工具' : msg.role}】
                                  </div>
                                  <div className="whitespace-pre-wrap break-words">
                                      {typeof contentDisplay === 'string' ? contentDisplay : contentDisplay}
                                  </div>
                                  
                                  {/* Handle Tool Calls in Request History (Assistant Role) */}
                                  {msg.tool_calls && Array.isArray(msg.tool_calls) && (
                                      <div className="mt-2 pl-2 border-l-2 border-primary/50">
                                          <div className="text-xs font-medium mb-1 text-primary">🛠️ 工具调用:</div>
                                          {msg.tool_calls.map((tc: any, i: number) => (
                                              <div key={i} className="font-mono text-xs bg-background p-2 rounded border mb-1">
                                                  <div className="font-bold text-primary">{tc.function?.name || 'unknown'}</div>
                                                  <div className="text-muted-foreground break-all">{tc.function?.arguments}</div>
                                              </div>
                                          ))}
                                      </div>
                                  )}
                              </div>
                          );
                      })}
                  </div>
              );
          }

          // Response Logic (Single message object or content/tool_calls dict)
          if (isResponse) {
               return (
                  <div className="bg-muted p-3 rounded-md text-sm">
                      <div className="font-semibold mb-1 text-xs text-muted-foreground uppercase">
                          【助手】
                      </div>
                      {data.content && (
                          <div className="whitespace-pre-wrap break-words mb-2">{data.content}</div>
                      )}
                      {data.tool_calls && Array.isArray(data.tool_calls) && (
                          <div className="mt-2 pl-2 border-l-2 border-primary/50">
                              <div className="text-xs font-medium mb-1 text-primary">🛠️ 工具调用:</div>
                              {data.tool_calls.map((tc: any, idx: number) => (
                                  <div key={idx} className="font-mono text-xs bg-background p-2 rounded border mb-1">
                                      <div className="font-bold text-primary">{tc.function?.name || 'unknown'}</div>
                                      <div className="text-muted-foreground break-all">{tc.function?.arguments}</div>
                                  </div>
                              ))}
                          </div>
                      )}
                       {/* Fallback for raw error or other formats */}
                       {!data.content && !data.tool_calls && (
                           <pre className="text-xs">{JSON.stringify(data, null, 2)}</pre>
                       )}
                  </div>
               );
          }

          // Fallback
          return <pre className="text-xs font-mono overflow-auto">{JSON.stringify(data, null, 2)}</pre>;
      } catch (e) {
          return <pre className="text-xs font-mono text-red-500 overflow-auto">{jsonStr}</pre>;
      }
  };

  const TRACE_STAGE_MAP: Record<string, string> = {
    "REQ_RECEIVED": "请求接收",
    "ROUTER_START": "意图识别开始",
    "ROUTER_END": "意图识别结束",
    "ROUTER_FAIL": "意图识别失败",
    "MODEL_CALL_START": "模型调用开始",
    "FIRST_TOKEN": "首包到达",
    "FULL_RESPONSE": "完整响应",
    "MODEL_FAIL": "调用失败",
    "ALL_FAILED": "全部失败"
  };

  if (authError) {
      return (
          <div className="flex flex-col items-center justify-center h-[60vh] space-y-4">
              <Lock className="h-16 w-16 text-muted-foreground" />
              <h2 className="text-2xl font-bold">需要授权</h2>
              <p className="text-muted-foreground">访问此页面需要 Gateway API Key</p>
              <div className="flex gap-2">
                  <Input 
                    type="password" 
                    placeholder="输入 API Key" 
                    value={apiKey} 
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-[300px]"
                  />
                  <Button onClick={saveApiKey}>确认</Button>
              </div>
          </div>
      );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 md:gap-0">
            <div>
            <h2 className="text-3xl font-bold tracking-tight">实时日志</h2>
            <p className="text-muted-foreground">查看所有请求的详细记录和调试信息。</p>
            </div>
            <div className="flex items-center gap-4">
            <div className="flex items-center space-x-2">
                <Switch 
                id="auto-refresh" 
                checked={autoRefresh} 
                onCheckedChange={setAutoRefresh}
                />
                <Label htmlFor="auto-refresh">自动刷新</Label>
            </div>
            <Button variant="outline" onClick={handleExport} className="gap-2">
                <Download className="h-4 w-4" /> 导出
            </Button>
            <Button onClick={loadData} disabled={loading} className="gap-2">
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> 刷新
            </Button>
            </div>
        </div>

        {/* Filter Bar */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 bg-muted/30 p-4 rounded-lg border">
            <div className="space-y-1">
                <Label className="text-xs">级别 (Level)</Label>
                <Select
                    value={filters.level || 'all'}
                    onValueChange={(value) => setFilters({...filters, level: value})}
                >
                    <SelectTrigger className="h-9">
                        <SelectValue placeholder="Select level" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">全部</SelectItem>
                        <SelectItem value="t1">T1</SelectItem>
                        <SelectItem value="t2">T2</SelectItem>
                        <SelectItem value="t3">T3</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <div className="space-y-1">
                <Label className="text-xs">状态 (Status)</Label>
                <Select
                    value={filters.status || 'all'}
                    onValueChange={(value) => setFilters({...filters, status: value})}
                >
                    <SelectTrigger className="h-9">
                        <SelectValue placeholder="选择状态" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">全部</SelectItem>
                        <SelectItem value="success">成功</SelectItem>
                        <SelectItem value="error">失败</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <div className="space-y-1">
                <Label className="text-xs">模型 (Model)</Label>
                <Input 
                    className="h-9" 
                    placeholder="Search model..." 
                    value={filters.model || ''}
                    onChange={(e) => setFilters({...filters, model: e.target.value})}
                />
            </div>
            <div className="space-y-1">
                <Label className="text-xs">开始时间</Label>
                <Popover>
                    <PopoverTrigger asChild>
                        <Button
                            variant={"outline"}
                            className={cn(
                                "h-9 w-full justify-start text-left font-normal",
                                !startDate && "text-muted-foreground"
                            )}
                        >
                            <CalendarIcon className="mr-2 h-4 w-4" />
                            {startDate ? format(startDate, "PPP") : <span>Pick a date</span>}
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                        <Calendar
                            mode="single"
                            selected={startDate}
                            onSelect={setStartDate}
                            initialFocus
                        />
                    </PopoverContent>
                </Popover>
            </div>
            <div className="space-y-1">
                <Label className="text-xs">结束时间</Label>
                <Popover>
                    <PopoverTrigger asChild>
                        <Button
                            variant={"outline"}
                            className={cn(
                                "h-9 w-full justify-start text-left font-normal",
                                !endDate && "text-muted-foreground"
                            )}
                        >
                            <CalendarIcon className="mr-2 h-4 w-4" />
                            {endDate ? format(endDate, "PPP") : <span>Pick a date</span>}
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                        <Calendar
                            mode="single"
                            selected={endDate}
                            onSelect={setEndDate}
                            initialFocus
                        />
                    </PopoverContent>
                </Popover>
            </div>
        </div>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <Table className="min-w-[800px]">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">时间</TableHead>
                <TableHead className="w-[100px]">等级</TableHead>
                <TableHead className="w-[150px]">模型</TableHead>
                <TableHead className="w-[100px]">耗时</TableHead>
                <TableHead className="w-[100px]">状态</TableHead>
                <TableHead>Prompt 预览</TableHead>
                <TableHead className="w-[80px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((log) => (
                <Sheet key={log.id}>
                  <SheetTrigger asChild>
                    <TableRow className="cursor-pointer hover:bg-muted/50">
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {/* Append 'Z' to indicate UTC time if missing, to ensure local conversion */}
                        {new Date(log.timestamp.endsWith('Z') ? log.timestamp : log.timestamp + 'Z').toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <Badge variant={log.level === 't3' ? 'destructive' : log.level === 't2' ? 'default' : 'secondary'}>
                            {log.level.toUpperCase()}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm">{log.model}</TableCell>
                      <TableCell className="text-sm font-mono">{log.duration_ms.toFixed(0)}ms</TableCell>
                      <TableCell>
                        {log.status === 'success' ? (
                          <div className="flex items-center gap-1 text-green-600 text-sm">
                             <CheckCircle2 className="h-4 w-4" /> 成功
                          </div>
                        ) : (
                           <div className="flex items-center gap-1 text-red-600 text-sm">
                             <XCircle className="h-4 w-4" /> 失败
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[300px] truncate text-muted-foreground text-sm">
                        {log.user_prompt_preview}
                      </TableCell>
                      <TableCell>
                        <Button variant="ghost" size="icon">
                            <FileText className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  </SheetTrigger>
                  <SheetContent className="w-full sm:w-[600px] overflow-y-auto max-w-[100vw]">
                    <SheetHeader>
                      <SheetTitle className="text-left">请求详情 #{log.id}</SheetTitle>
                      <SheetDescription className="text-left">
                         {new Date(log.timestamp.endsWith('Z') ? log.timestamp : log.timestamp + 'Z').toLocaleString()}
                      </SheetDescription>
                    </SheetHeader>
                    <div className="mt-6 space-y-6">
                       <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                          <div>
                              <span className="text-muted-foreground">等级:</span> {log.level}
                          </div>
                           <div>
                              <span className="text-muted-foreground">模型:</span> {log.model}
                          </div>
                           <div>
                              <span className="text-muted-foreground">耗时:</span> {log.duration_ms.toFixed(2)}ms
                          </div>
                           <div>
                              <span className="text-muted-foreground">状态:</span> {log.status}
                          </div>
                          {log.retry_count !== undefined && (
                              <div>
                                  <span className="text-muted-foreground">重试次数:</span> {log.retry_count}
                              </div>
                          )}
                       </div>

                      {/* Stack Trace for Errors */}
                      {log.stack_trace && (
                          <div className="border-l-4 border-red-500 bg-red-50 p-4 rounded-r-md overflow-hidden">
                              <h4 className="text-sm font-bold text-red-700 mb-2">错误堆栈</h4>
                              <div className="overflow-x-auto">
                                <pre className="text-xs text-red-600 font-mono whitespace-pre-wrap break-all sm:break-normal sm:whitespace-pre-wrap">
                                    {log.stack_trace}
                                </pre>
                              </div>
                          </div>
                      )}

                      {log.trace && (
                        <div className="mb-4">
                          <h4 className="text-sm font-medium mb-2">执行追踪 (Trace)</h4>
                          {/* Token Usage Display */}
                          {((log.prompt_tokens ?? 0) > 0 || (log.completion_tokens ?? 0) > 0) && (
                            <div className="flex gap-4 mb-3 p-3 bg-muted/50 rounded-lg border border-dashed">
                                <div className="flex flex-col">
                                    <span className="text-[10px] text-muted-foreground uppercase">Prompt Tokens</span>
                                    <span className="font-mono font-bold text-sky-600">{log.prompt_tokens}</span>
                                </div>
                                <div className="flex flex-col">
                                    <span className="text-[10px] text-muted-foreground uppercase">Completion Tokens</span>
                                    <span className="font-mono font-bold text-emerald-600">{log.completion_tokens}</span>
                                </div>
                                <div className="flex flex-col border-l pl-4">
                                    <span className="text-[10px] text-muted-foreground uppercase">Total</span>
                                    <span className="font-mono font-bold text-foreground">{(log.prompt_tokens ?? 0) + (log.completion_tokens ?? 0)}</span>
                                </div>
                            </div>
                          )}
                          <div className="space-y-3 relative before:absolute before:left-[19px] before:top-2 before:bottom-2 before:w-[2px] before:bg-border">
                            {(() => {
                              try {
                                const trace: TraceEvent[] = JSON.parse(log.trace);
                                return trace.map((event, i) => (
                                  <div key={i} className="flex items-start gap-3 text-sm relative">
                                    {i < trace.length - 1 && (
                                      <div className="absolute left-[9px] top-6 bottom-[-16px] w-[1px] bg-border" />
                                    )}
                                    <div className={`w-5 h-5 min-w-[1.25rem] rounded-full flex items-center justify-center text-[10px] z-10 
                                      ${event.status === 'success' ? 'bg-green-100 text-green-700' : event.status === 'fail' ? 'bg-red-100 text-red-700' : 'bg-slate-100'}`}>
                                      {i + 1}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                      <div className="flex justify-between items-start sm:items-center flex-col sm:flex-row gap-1 sm:gap-0">
                                        <div className="flex flex-col min-w-0">
                                            <span className="font-medium truncate">{TRACE_STAGE_MAP[event.stage] || event.stage}</span>
                                            {event.model && (
                                                <span className="text-[10px] text-muted-foreground font-mono truncate">
                                                    {event.model}
                                                </span>
                                            )}
                                            {event.reason && (
                                                <span className="text-[10px] text-red-500 font-mono mt-0.5 break-words">
                                                    {event.reason}
                                                </span>
                                            )}
                                        </div>
                                        <span className="text-xs text-muted-foreground font-mono whitespace-nowrap">
                                          {["REQ_RECEIVED", "ROUTER_START", "MODEL_CALL_START"].includes(event.stage) ? '' : '+'}
                                          {event.duration_ms.toFixed(0)}ms
                                        </span>
                                      </div>
                                      <div className="text-xs text-muted-foreground flex gap-2 mt-1 sm:mt-0">
                                        <span>{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
                                        {event.retry_count > 0 && (
                                          <span className="text-orange-500 whitespace-nowrap">Retry #{event.retry_count}</span>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ));
                              } catch (e) {
                                return <div className="text-red-500 text-xs">无法解析 Trace 数据</div>;
                              }
                            })()}
                          </div>
                        </div>
                      )}

                      <div>
                        <h4 className="text-sm font-medium mb-2">请求体 (Request JSON)</h4>
                        <div className="bg-muted p-4 rounded-md overflow-auto max-h-[400px]">
                          {renderMessageContent(log.full_request, false)}
                        </div>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium mb-2">响应体 (Response JSON)</h4>
                         <div className="bg-muted p-4 rounded-md overflow-auto max-h-[400px]">
                          {renderMessageContent(log.full_response, true)}
                        </div>
                      </div>
                    </div>
                  </SheetContent>
                </Sheet>
              ))}
            </TableBody>
          </Table>
        </CardContent>
        {total > pageSize && (
            <div className="p-4 flex justify-center gap-2 border-t">
                <Button 
                    variant="outline" 
                    disabled={page === 1} 
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                >
                    上一页
                </Button>
                <span className="flex items-center text-sm text-muted-foreground">
                    第 {page} 页 / 共 {Math.ceil(total / pageSize)} 页
                </span>
                <Button 
                    variant="outline" 
                    disabled={page * pageSize >= total} 
                    onClick={() => setPage(p => p + 1)}
                >
                    下一页
                </Button>
            </div>
        )}
      </Card>
    </div>
  );
}