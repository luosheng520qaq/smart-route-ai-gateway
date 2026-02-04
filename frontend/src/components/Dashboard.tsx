import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { PieChart, Pie, Cell, ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { Activity, Clock, AlertTriangle, RefreshCcw, HeartPulse, Coins, Info } from 'lucide-react';
import { fetchStats, fetchModelStats, Stats } from '@/lib/api';
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip as UITooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const COLORS = ['#0ea5e9', '#22d3ee', '#94a3b8', '#cbd5e1']; // Sky, Cyan, Slate, Light Slate

// Utility to format date for chart
const formatChartDate = (isoStr: string) => {
  const date = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z');
  return `${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
};

import { ChevronDown, ChevronUp } from 'lucide-react';

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [modelStats, setModelStats] = useState<Record<string, { failures: number; success: number; health_score?: number }> | null>(null);
  const [loading, setLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(false);
  const [timeRange, setTimeRange] = useState<'today' | '3days' | 'all'>('today');

  const loadData = async () => {
    try {
      // Fetch stats and model stats in parallel
      const [statsData, modelStatsData] = await Promise.all([
        fetchStats(timeRange),
        fetchModelStats()
      ]);
      setStats(statsData);
      setModelStats(modelStatsData);
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
  }, [timeRange]); // Reload when range changes

  const handleResetZoom = () => {
    console.log("Reset zoom");
  };

  if (loading && !stats) return <div className="p-8 text-slate-500 animate-pulse">加载数据中...</div>;

  const chartData = stats?.response_trend.map(item => ({
    ...item,
    time: formatChartDate(item.time),
    value: Math.round(item.duration) // Integer ms
  })) || [];

  // Calculate Health/Weight for Model Stats
  const modelHealthData = Object.entries(modelStats || {}).map(([model, data]: [string, any]) => {
      // Use health_score from backend if available, otherwise fallback (for safety)
      const health = data.health_score !== undefined ? data.health_score : Math.round((1.0 / (1.0 + (data.failures || 0) * 0.2)) * 100);
      
      return {
          model,
          success: data.success,
          failures: data.failures,
          health: health
      };
  }).sort((a, b) => a.health - b.health); // Sort by health asc (problematic ones first)

  const visibleModels = isExpanded ? modelHealthData : modelHealthData.slice(0, 3);

  return (
    <div className="space-y-6 animate-in fade-in duration-700 slide-in-from-bottom-4">
      {/* Header & Filter */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
         <div>
            <h2 className="text-2xl font-bold tracking-tight">仪表盘</h2>
            <p className="text-muted-foreground">实时监控系统状态与模型性能</p>
         </div>
         <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">统计范围:</span>
            <Select value={timeRange} onValueChange={(v: any) => setTimeRange(v)}>
                <SelectTrigger className="w-[140px]">
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="today">今日 (24h)</SelectItem>
                    <SelectItem value="3days">最近三天</SelectItem>
                    <SelectItem value="all">全部历史</SelectItem>
                </SelectContent>
            </Select>
         </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="group hover:border-sky-400/50 transition-all duration-300">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-sky-500 transition-colors">请求总数</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground group-hover:text-sky-500 transition-colors" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-sky-500 to-cyan-500">{stats?.total_requests}</div>
            <p className="text-xs text-muted-foreground mt-1">
              较上个周期 <span className={`font-medium ${
                (stats?.request_change_percentage || 0) > 0 ? 'text-emerald-500' : 
                (stats?.request_change_percentage || 0) < 0 ? 'text-rose-500' : 'text-muted-foreground'
              }`}>
                {(stats?.request_change_percentage || 0) > 0 ? '+' : ''}{stats?.request_change_percentage || 0}%
              </span>
            </p>
          </CardContent>
        </Card>
        <Card className="group hover:border-cyan-400/50 transition-all duration-300">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-cyan-500 transition-colors">平均延迟</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground group-hover:text-cyan-500 transition-colors" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-500 to-teal-400">{stats?.avg_duration} <span className="text-sm text-foreground/50">ms</span></div>
            <p className="text-xs text-muted-foreground mt-1">全局平均响应时间</p>
          </CardContent>
        </Card>
        <Card className="group hover:border-rose-400/50 transition-all duration-300">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-rose-500 transition-colors">错误率</CardTitle>
            <AlertTriangle className={`h-4 w-4 ${stats?.error_rate && stats.error_rate > 5 ? 'text-rose-500' : 'text-muted-foreground group-hover:text-rose-500'} transition-colors`} />
          </CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold ${stats?.error_rate && stats.error_rate > 5 ? 'text-rose-500' : 'bg-clip-text text-transparent bg-gradient-to-r from-slate-400 to-slate-600'}`}>{stats?.error_rate}%</div>
            <p className="text-xs text-muted-foreground mt-1">故障切换触发频率</p>
          </CardContent>
        </Card>
        
        {/* Token Usage Card */}
        <Card className="group hover:border-amber-400/50 transition-all duration-300">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-amber-500 transition-colors">Token 消耗</CardTitle>
            <Coins className="h-4 w-4 text-muted-foreground group-hover:text-amber-500 transition-colors" />
          </CardHeader>
          <CardContent>
             <TooltipProvider>
                <UITooltip>
                    <TooltipTrigger asChild>
                        <div className="cursor-help">
                            <div className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-amber-500 to-orange-500">
                                {stats?.tokens?.total ? (stats.tokens.total / 1000).toFixed(1) + 'k' : '0'}
                            </div>
                            <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                                <Info className="h-3 w-3" /> 查看输入/输出详情
                            </div>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent>
                        <div className="text-xs space-y-1">
                            <div className="font-semibold border-b pb-1 mb-1">Token 统计详情</div>
                            <div className="flex justify-between gap-4">
                                <span>Input (Prompt):</span>
                                <span className="font-mono">{stats?.tokens?.prompt?.toLocaleString() || 0}</span>
                            </div>
                            <div className="flex justify-between gap-4">
                                <span>Output (Completion):</span>
                                <span className="font-mono">{stats?.tokens?.completion?.toLocaleString() || 0}</span>
                            </div>
                             <div className="flex justify-between gap-4 border-t pt-1 mt-1 font-medium">
                                <span>Total:</span>
                                <span className="font-mono">{stats?.tokens?.total?.toLocaleString() || 0}</span>
                            </div>
                        </div>
                    </TooltipContent>
                </UITooltip>
            </TooltipProvider>
          </CardContent>
        </Card>
      </div>

      {/* Model Health Status */}
      <Card className="border-none shadow-sm bg-card/50">
        <CardHeader>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <HeartPulse className="h-5 w-5 text-rose-500" />
                    <CardTitle>模型健康度监控 (Adaptive Health)</CardTitle>
                </div>
                {modelHealthData.length > 3 && (
                    <Button variant="ghost" size="sm" onClick={() => setIsExpanded(!isExpanded)}>
                        {isExpanded ? (
                            <>
                                <ChevronUp className="h-4 w-4 mr-1" /> 收起
                            </>
                        ) : (
                            <>
                                <ChevronDown className="h-4 w-4 mr-1" /> 展开全部 ({modelHealthData.length})
                            </>
                        )}
                    </Button>
                )}
            </div>
            <CardDescription>
                实时监控各模型的成功/失败次数及自适应权重。权重越低，被调用的概率越小。
            </CardDescription>
        </CardHeader>
        <CardContent>
            {modelHealthData.length === 0 ? (
                <div className="text-center text-muted-foreground py-8">暂无模型调用数据</div>
            ) : (
                <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {visibleModels.map((m) => (
                            <div key={m.model} className="flex items-center justify-between p-3 border rounded-lg bg-background/50">
                                <div>
                                    <div className="font-medium text-sm truncate max-w-[150px]" title={m.model}>{m.model}</div>
                                    <div className="text-xs text-muted-foreground flex gap-2 mt-1">
                                        <span className="text-emerald-500">成功: {m.success}</span>
                                        <span className={m.failures > 0 ? "text-rose-500 font-bold" : "text-muted-foreground"}>失败: {m.failures}</span>
                                    </div>
                                </div>
                                <div className="text-right">
                                    <div className="text-xs text-muted-foreground mb-1">健康度</div>
                                    <div className={`text-lg font-bold ${m.health < 50 ? 'text-rose-500' : m.health < 80 ? 'text-yellow-500' : 'text-emerald-500'}`}>
                                        {m.health}%
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </CardContent>
      </Card>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="col-span-1 border-none shadow-none bg-transparent">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <span className="w-1 h-6 bg-sky-500 rounded-full"></span>
              意图分布
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[300px] glass rounded-2xl p-4">
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
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>响应时间趋势 (最近50次)</CardTitle>
            <Button variant="outline" size="sm" onClick={handleResetZoom}>
               <RefreshCcw className="h-3 w-3 mr-1" /> 重置缩放
            </Button>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <XAxis 
                  dataKey="time" 
                  tick={{fontSize: 10}}
                  interval="preserveStartEnd"
                />
                <YAxis 
                   tickFormatter={(val) => `${val}ms`}
                   domain={[0, 'auto']}
                   width={40}
                   tick={{fontSize: 10}}
                />
                <Tooltip 
                   formatter={(value: any) => [`${value} ms`, "Duration"]}
                   labelStyle={{color: '#666'}}
                   contentStyle={{borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}}
                />
                <Line 
                  type="monotone" 
                  dataKey="value" 
                  stroke="#0ea5e9" 
                  strokeWidth={2} 
                  dot={(props: any) => {
                      const { cx, cy, payload } = props;
                      let fill = "#22c55e"; // Green < 1000
                      if (payload.value > 3000) fill = "#ef4444"; // Red > 3000
                      else if (payload.value > 1000) fill = "#eab308"; // Yellow > 1000
                      
                      return <circle cx={cx} cy={cy} r={3} stroke="none" fill={fill} key={payload.time} />;
                  }}
                  activeDot={{ r: 6, stroke: '#0ea5e9', strokeWidth: 2, fill: '#fff' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
