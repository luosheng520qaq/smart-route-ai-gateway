import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription } from "@/components/ui/sheet";
import { PieChart, Pie, Cell, ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { Activity, Clock, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { fetchLogs, fetchStats, RequestLog, Stats } from '@/lib/api';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [logs, setLogs] = useState<RequestLog[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const [statsData, logsData] = await Promise.all([fetchStats(), fetchLogs(1, 10)]);
      setStats(statsData);
      setLogs(logsData.logs);
    } catch (error) {
      console.error("Failed to load dashboard data", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, []);

  if (loading && !stats) return <div className="p-8 text-slate-600">加载数据中...</div>;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">今日请求总数</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_requests}</div>
            <p className="text-xs text-muted-foreground">较昨日 +20.1%</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">平均延迟</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.avg_duration} ms</div>
            <p className="text-xs text-muted-foreground">全局平均</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">错误率</CardTitle>
            <AlertTriangle className={`h-4 w-4 ${stats?.error_rate && stats.error_rate > 5 ? 'text-red-500' : 'text-muted-foreground'}`} />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${stats?.error_rate && stats.error_rate > 5 ? 'text-red-500' : ''}`}>{stats?.error_rate}%</div>
            <p className="text-xs text-muted-foreground">故障切换事件</p>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>意图分布</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={stats?.intent_distribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  fill="#8884d8"
                  paddingAngle={5}
                  dataKey="value"
                >
                  {stats?.intent_distribution.map((_entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>响应时间趋势 (最近50次)</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats?.response_trend}>
                <XAxis dataKey="time" hide />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="duration" stroke="#8884d8" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Logs */}
      <Card>
        <CardHeader>
          <CardTitle>最近请求</CardTitle>
          <CardDescription>点击某一行查看完整详情。</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>等级</TableHead>
                <TableHead>模型</TableHead>
                <TableHead>耗时</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>预览</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((log) => (
                <Sheet key={log.id}>
                  <SheetTrigger asChild>
                    <TableRow className="cursor-pointer hover:bg-muted/50">
                      <TableCell>{new Date(log.timestamp).toLocaleTimeString()}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{log.level}</Badge>
                      </TableCell>
                      <TableCell>{log.model}</TableCell>
                      <TableCell>{log.duration_ms.toFixed(0)}ms</TableCell>
                      <TableCell>
                        {log.status === 'success' ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500" />
                        )}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-muted-foreground">
                        {log.user_prompt_preview}
                      </TableCell>
                    </TableRow>
                  </SheetTrigger>
                  <SheetContent className="w-[600px] sm:w-[540px] overflow-y-auto">
                    <SheetHeader>
                      <SheetTitle>请求详情 #{log.id}</SheetTitle>
                      <SheetDescription>
                        {new Date(log.timestamp).toLocaleString()} | {log.model}
                      </SheetDescription>
                    </SheetHeader>
                    <div className="mt-6 space-y-6">
                      <div>
                        <h4 className="text-sm font-medium mb-2">请求体 (Request Body)</h4>
                        <div className="bg-muted p-4 rounded-md text-xs font-mono overflow-auto max-h-[300px]">
                          <pre>{JSON.stringify(JSON.parse(log.full_request), null, 2)}</pre>
                        </div>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium mb-2">响应体 (Response Body)</h4>
                         <div className="bg-muted p-4 rounded-md text-xs font-mono overflow-auto max-h-[300px]">
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
      </Card>
    </div>
  );
}
