import { useEffect, useState } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { CheckCircle2, XCircle, RefreshCw, FileText } from 'lucide-react';
import { fetchLogs, RequestLog, TraceEvent } from '@/lib/api';

export function LogsPage() {
  const [logs, setLogs] = useState<RequestLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const pageSize = 50;

  const loadData = async () => {
    setLoading(true);
    try {
      const logsData = await fetchLogs(page, pageSize);
      setLogs(logsData.logs);
      setTotal(logsData.total);
    } catch (error) {
      console.error("Failed to load logs", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [page]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (autoRefresh) {
      interval = setInterval(() => {
        // Only refresh if on first page to avoid jumping
        if (page === 1) {
            fetchLogs(1, pageSize).then(data => {
                setLogs(data.logs);
                setTotal(data.total);
            });
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [autoRefresh, page]);

  return (
    <div className="space-y-6 animate-in fade-in duration-500 pb-20">
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
          <Button onClick={loadData} disabled={loading} className="gap-2">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> 刷新
          </Button>
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
                  <SheetContent className="w-[800px] sm:w-[600px] overflow-y-auto">
                    <SheetHeader>
                      <SheetTitle>请求详情 #{log.id}</SheetTitle>
                      <SheetDescription>
                         {new Date(log.timestamp.endsWith('Z') ? log.timestamp : log.timestamp + 'Z').toLocaleString()}
                      </SheetDescription>
                    </SheetHeader>
                    <div className="mt-6 space-y-6">
                       <div className="grid grid-cols-2 gap-4 text-sm">
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
                       </div>

                      {/* Trace Timeline */}
                      {log.trace && (
                        <div>
                          <h4 className="text-sm font-medium mb-2">调用链路追踪 (Trace)</h4>
                          <div className="border rounded-md p-4 space-y-4">
                            {(() => {
                              try {
                                const trace: TraceEvent[] = JSON.parse(log.trace);
                                return trace.map((event, i) => (
                                  <div key={i} className="flex items-start gap-3 text-sm relative">
                                    {i < trace.length - 1 && (
                                      <div className="absolute left-[9px] top-6 bottom-[-16px] w-[1px] bg-border" />
                                    )}
                                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] z-10 
                                      ${event.status === 'success' ? 'bg-green-100 text-green-700' : event.status === 'fail' ? 'bg-red-100 text-red-700' : 'bg-slate-100'}`}>
                                      {i + 1}
                                    </div>
                                    <div className="flex-1">
                                      <div className="flex justify-between items-center">
                                        <span className="font-medium">{event.stage}</span>
                                        <span className="text-xs text-muted-foreground font-mono">
                                          +{event.duration_ms.toFixed(0)}ms
                                        </span>
                                      </div>
                                      <div className="text-xs text-muted-foreground flex gap-2">
                                        <span>{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
                                        {event.retry_count > 0 && (
                                          <span className="text-orange-500">Retry #{event.retry_count}</span>
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
                        <div className="bg-muted p-4 rounded-md text-xs font-mono overflow-auto max-h-[400px]">
                          <pre>{JSON.stringify(JSON.parse(log.full_request), null, 2)}</pre>
                        </div>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium mb-2">响应体 (Response JSON)</h4>
                         <div className="bg-muted p-4 rounded-md text-xs font-mono overflow-auto max-h-[400px]">
                          <pre>{JSON.stringify(JSON.parse(log.full_response), null, 2)}</pre>
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
