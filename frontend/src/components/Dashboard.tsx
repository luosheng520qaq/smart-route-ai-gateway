import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PieChart, Pie, Cell, ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { Activity, Clock, AlertTriangle, RefreshCcw } from 'lucide-react';
import { fetchStats, Stats } from '@/lib/api';
import { Button } from "@/components/ui/button";

const COLORS = ['#0ea5e9', '#22d3ee', '#94a3b8', '#cbd5e1']; // Sky, Cyan, Slate, Light Slate

// Utility to format date for chart
const formatChartDate = (isoStr: string) => {
  const date = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z');
  return `${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
};

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  // Remove unused logs state for now, as Dashboard only shows charts and stats cards
  // const [logs, setLogs] = useState<RequestLog[]>([]); 
  const [loading, setLoading] = useState(true);
  // const [chartZoom, setChartZoom] = useState<{ left?: string, right?: string }>({}); // Prepared for future zoom implementation

  const loadData = async () => {
    try {
      // Just fetch stats for dashboard view
      const statsData = await fetchStats();
      setStats(statsData);
      // const logsData = await fetchLogs(1, 10);
      // setLogs(logsData.logs);
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

  const handleResetZoom = () => {
    // Reset logic placeholder if we implement interactive zoom later
    // setChartZoom({});
    console.log("Reset zoom");
  };

  if (loading && !stats) return <div className="p-8 text-slate-500 animate-pulse">加载数据中...</div>;

  const chartData = stats?.response_trend.map(item => ({
    ...item,
    time: formatChartDate(item.time),
    value: Math.round(item.duration) // Integer ms
  })) || [];

  return (
    <div className="space-y-6 animate-in fade-in duration-700 slide-in-from-bottom-4">
      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="group hover:border-sky-400/50 transition-all duration-300">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-sky-500 transition-colors">今日请求总数</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground group-hover:text-sky-500 transition-colors" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-sky-500 to-cyan-500">{stats?.total_requests}</div>
            <p className="text-xs text-muted-foreground mt-1">较昨日 <span className="text-emerald-500 font-medium">+20.1%</span></p>
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
      </div>

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
                   domain={['auto', 'auto']}
                />
                <Tooltip 
                   formatter={(value: any) => [`${value} ms`, "Duration"]}
                   labelStyle={{color: '#666'}}
                />
                <Line 
                  type="monotone" 
                  dataKey="value" 
                  stroke="#8884d8" 
                  strokeWidth={2} 
                  dot={(props: any) => {
                      const { cx, cy, payload } = props;
                      let fill = "#22c55e"; // Green < 1000
                      if (payload.value > 3000) fill = "#ef4444"; // Red > 3000
                      else if (payload.value > 1000) fill = "#eab308"; // Yellow > 1000
                      
                      return <circle cx={cx} cy={cy} r={4} stroke="none" fill={fill} key={payload.time} />;
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
