import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Save, Plus, Trash2, Brain, HeartPulse, ShieldCheck, Settings, Server, Network, History as HistoryIcon, RotateCcw, Database } from 'lucide-react';
import { AppConfig, fetchConfig, updateConfig, fetchHistory, rollbackConfig, ConfigHistory } from '@/lib/api';
import { Setup2FA } from './AuthPage';
import { ChangePassword } from './ChangePassword';
import { ChangeUsername } from './ChangeUsername';
import { useAuth } from '@/lib/auth';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function ConfigPage() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const { has2FA, checkAuth } = useAuth();

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const data = await fetchConfig();
      setConfig(data);
    } catch (error) {
      toast.error("加载配置失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config) return;
    try {
      await updateConfig(config);
      toast.success("配置保存成功");
    } catch (error) {
      toast.error("配置保存失败: " + (error as any).message);
    }
  };

  if (loading || !config) return <div className="p-8 text-center">加载配置中...</div>;

  return (
    <div className="space-y-6 max-w-6xl mx-auto animate-in fade-in duration-500 pb-20">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 md:gap-0 border-b pb-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">配置管理中心</h2>
          <p className="text-muted-foreground">全功能系统配置与策略管理</p>
        </div>
        <div className="flex gap-2">
           <HistoryDialog onRollback={loadConfig} />
           <Button onClick={handleSave} className="gap-2">
            <Save className="h-4 w-4" /> 保存更改
          </Button>
        </div>
      </div>

      <Tabs defaultValue="general" className="w-full flex flex-col md:flex-row gap-6">
        <TabsList className="flex md:flex-col h-auto justify-start w-full md:w-48 bg-transparent p-0 gap-2 overflow-x-auto no-scrollbar">
            <TabItem value="general" icon={<Settings className="w-4 h-4"/>} label="基础设置" />
            <TabItem value="models" icon={<Server className="w-4 h-4"/>} label="模型管理" />
            <TabItem value="providers" icon={<Database className="w-4 h-4"/>} label="供应商" />
            <TabItem value="resilience" icon={<HeartPulse className="w-4 h-4"/>} label="稳定性" />
            <TabItem value="router" icon={<Brain className="w-4 h-4"/>} label="意图路由" />
            <TabItem value="params" icon={<Network className="w-4 h-4"/>} label="参数调优" />
            <TabItem value="security" icon={<ShieldCheck className="w-4 h-4"/>} label="安全设置" />
        </TabsList>

        <div className="flex-1 space-y-6">
            <TabsContent value="general" className="m-0 space-y-6">
                <GeneralSettings config={config} setConfig={setConfig} />
            </TabsContent>
            
            <TabsContent value="models" className="m-0 space-y-6">
                <ModelSettings config={config} setConfig={setConfig} />
            </TabsContent>

            <TabsContent value="providers" className="m-0 space-y-6">
                <ProviderSettings config={config} setConfig={setConfig} />
            </TabsContent>

            <TabsContent value="resilience" className="m-0 space-y-6">
                <ResilienceSettings config={config} setConfig={setConfig} />
            </TabsContent>

            <TabsContent value="router" className="m-0 space-y-6">
                <RouterSettings config={config} setConfig={setConfig} />
            </TabsContent>

             <TabsContent value="params" className="m-0 space-y-6">
                <ParamSettings config={config} setConfig={setConfig} />
            </TabsContent>

            <TabsContent value="security" className="m-0 space-y-6">
                <SecuritySettings config={config} setConfig={setConfig} has2FA={has2FA} checkAuth={checkAuth} />
            </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

function TabItem({ value, icon, label }: { value: string, icon: any, label: string }) {
    return (
        <TabsTrigger 
            value={value}
            className="flex-shrink-0 md:w-full justify-start gap-2 px-4 py-3 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all"
        >
            {icon}
            {label}
        </TabsTrigger>
    )
}

// --- Sub-Components ---

function GeneralSettings({ config, setConfig }: { config: AppConfig, setConfig: any }) {
    return (
        <Card>
            <CardHeader>
                <CardTitle>基础设置</CardTitle>
                <CardDescription>系统全局参数配置</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-2">
                    <Label>日志保留天数</Label>
                    <div className="flex items-center gap-4">
                        <Slider 
                            value={[config.general.log_retention_days]} 
                            min={1} max={365} step={1}
                            onValueChange={(val) => setConfig({...config, general: {...config.general, log_retention_days: val[0]}})}
                            className="flex-1"
                        />
                        <span className="w-12 text-center">{config.general.log_retention_days} 天</span>
                    </div>
                </div>
                 <div className="space-y-2">
                    <Label>Gateway API Key</Label>
                    <Input 
                        type="password"
                        value={config.general.gateway_api_key}
                        onChange={(e) => setConfig({...config, general: {...config.general, gateway_api_key: e.target.value}})}
                        placeholder="留空允许所有访问"
                    />
                    <p className="text-xs text-muted-foreground">用于保护 OpenAI 接口访问。</p>
                </div>
            </CardContent>
        </Card>
    )
}

function ModelSettings({ config, setConfig }: { config: AppConfig, setConfig: any }) {
    const updateList = (level: 't1' | 't2' | 't3', list: string[]) => {
        setConfig({...config, models: {...config.models, [level]: list}});
    };

    return (
        <Tabs defaultValue="t1" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="t1">T1 (快速)</TabsTrigger>
                <TabsTrigger value="t2">T2 (通用)</TabsTrigger>
                <TabsTrigger value="t3">T3 (高智商)</TabsTrigger>
            </TabsList>

            {['t1', 't2', 't3'].map((level) => (
                <TabsContent key={level} value={level} className="mt-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="uppercase">{level} 模型池</CardTitle>
                            <CardDescription>
                                {level === 't1' ? '快速/低成本模型' : level === 't2' ? '通用智能模型' : '高智商/复杂任务模型'}
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex items-center justify-between">
                                <Label>路由策略</Label>
                                <Select 
                                    value={config.models.strategies[level] || "sequential"}
                                    onValueChange={(val) => setConfig({
                                        ...config, 
                                        models: {
                                            ...config.models, 
                                            strategies: {...config.models.strategies, [level]: val}
                                        }
                                    })}
                                >
                                    <SelectTrigger className="w-[180px]">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="sequential">顺序优先</SelectItem>
                                        <SelectItem value="random">随机负载</SelectItem>
                                        <SelectItem value="adaptive">自适应(错误率)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>

                            {(config.models.strategies[level] || "sequential") === "sequential" ? (
                                <div className="flex items-center justify-between">
                                    <Label>最多顺序几轮 (完整尝试完一个列表算一轮)</Label>
                                    <Input 
                                        type="number" 
                                        className="w-[180px]"
                                        min={1}
                                        value={config.retries.rounds[level] || 1}
                                        onChange={(e) => setConfig({
                                            ...config,
                                            retries: {
                                                ...config.retries,
                                                rounds: {...config.retries.rounds, [level]: parseInt(e.target.value) || 1}
                                            }
                                        })}
                                    />
                                </div>
                            ) : (
                                <div className="flex items-center justify-between">
                                    <Label>最大重试模型次数 (切换一个模型算一次)</Label>
                                    <Input 
                                        type="number" 
                                        className="w-[180px]"
                                        min={1}
                                        value={config.retries.max_retries?.[level] || 3}
                                        onChange={(e) => setConfig({
                                            ...config,
                                            retries: {
                                                ...config.retries,
                                                max_retries: {...(config.retries.max_retries || {}), [level]: parseInt(e.target.value) || 1}
                                            }
                                        })}
                                    />
                                </div>
                            )}

                            <div className="space-y-2">
                                {config.models[level as 't1'|'t2'|'t3'].map((model, idx) => (
                                    <div key={idx} className="flex gap-2">
                                        <Input 
                                            value={model}
                                            onChange={(e) => {
                                                const newList = [...config.models[level as 't1'|'t2'|'t3']];
                                                newList[idx] = e.target.value;
                                                updateList(level as any, newList);
                                            }}
                                        />
                                        <Button variant="ghost" size="icon" onClick={() => {
                                            const newList = [...config.models[level as 't1'|'t2'|'t3']];
                                            newList.splice(idx, 1);
                                            updateList(level as any, newList);
                                        }}>
                                            <Trash2 className="h-4 w-4 text-red-500"/>
                                        </Button>
                                    </div>
                                ))}
                                <Button variant="outline" size="sm" onClick={() => {
                                    const newList = [...config.models[level as 't1'|'t2'|'t3'], ""];
                                    updateList(level as any, newList);
                                }}>
                                    <Plus className="h-4 w-4 mr-1"/> 添加模型
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            ))}
        </Tabs>
    )
}

function ProviderSettings({ config, setConfig }: { config: AppConfig, setConfig: any }) {
    return (
        <div className="space-y-6">
            <Card>
                <CardHeader>
                    <CardTitle>默认上游 (Upstream)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid gap-2">
                        <Label>Base URL</Label>
                        <Input 
                            value={config.providers.upstream.base_url}
                            onChange={(e) => setConfig({...config, providers: {...config.providers, upstream: {...config.providers.upstream, base_url: e.target.value}}})}
                        />
                    </div>
                    <div className="grid gap-2">
                        <Label>API Key</Label>
                        <Input 
                            type="password"
                            value={config.providers.upstream.api_key}
                            onChange={(e) => setConfig({...config, providers: {...config.providers, upstream: {...config.providers.upstream, api_key: e.target.value}}})}
                        />
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>自定义供应商 (Custom Providers)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {Object.entries(config.providers.custom).map(([key, provider]) => (
                        <div key={key} className="border p-4 rounded relative space-y-2">
                             <Button variant="ghost" size="icon" className="absolute top-2 right-2" onClick={() => {
                                const newCustom = {...config.providers.custom};
                                delete newCustom[key];
                                setConfig({...config, providers: {...config.providers, custom: newCustom}});
                            }}>
                                <Trash2 className="h-4 w-4 text-red-500"/>
                            </Button>
                            <div className="grid gap-2">
                                <Label>Provider ID</Label>
                                <Input value={key} disabled />
                            </div>
                            <div className="grid gap-2">
                                <Label>Base URL</Label>
                                <Input 
                                    value={provider.base_url}
                                    onChange={(e) => setConfig({
                                        ...config,
                                        providers: {
                                            ...config.providers,
                                            custom: {
                                                ...config.providers.custom,
                                                [key]: {...provider, base_url: e.target.value}
                                            }
                                        }
                                    })}
                                />
                            </div>
                            <div className="grid gap-2">
                                <Label>API Key</Label>
                                <Input 
                                    type="password"
                                    value={provider.api_key}
                                    onChange={(e) => setConfig({
                                        ...config,
                                        providers: {
                                            ...config.providers,
                                            custom: {
                                                ...config.providers.custom,
                                                [key]: {...provider, api_key: e.target.value}
                                            }
                                        }
                                    })}
                                />
                            </div>
                        </div>
                    ))}
                    <Button variant="outline" onClick={() => {
                        const id = prompt("输入 Provider ID (如 azure):");
                        if(id) {
                            setConfig({
                                ...config,
                                providers: {
                                    ...config.providers,
                                    custom: {
                                        ...config.providers.custom,
                                        [id]: {base_url: "", api_key: ""}
                                    }
                                }
                            })
                        }
                    }}>
                        <Plus className="h-4 w-4 mr-1"/> 添加供应商
                    </Button>
                </CardContent>
            </Card>
        </div>
    )
}

function ResilienceSettings({ config, setConfig }: { config: AppConfig, setConfig: any }) {
    return (
        <div className="space-y-6">
            <Card>
                <CardHeader><CardTitle>超时设置 (Timeouts)</CardTitle></CardHeader>
                <CardContent className="space-y-6">
                     {['t1', 't2', 't3'].map(level => (
                         <div key={level} className="space-y-2">
                             <Label className="uppercase">{level} 层级</Label>
                             <div className="grid grid-cols-2 gap-4">
                                 <div>
                                     <span className="text-xs text-muted-foreground">连接/首字超时 (ms)</span>
                                     <Input 
                                        type="number" 
                                        value={config.timeouts.connect[level] || 5000}
                                        onChange={(e) => setConfig({
                                            ...config,
                                            timeouts: {
                                                ...config.timeouts,
                                                connect: {...config.timeouts.connect, [level]: parseInt(e.target.value)}
                                            }
                                        })}
                                     />
                                 </div>
                                 <div>
                                     <span className="text-xs text-muted-foreground">生成超时 (ms)</span>
                                     <Input 
                                        type="number" 
                                        value={config.timeouts.generation[level] || 300000}
                                        onChange={(e) => setConfig({
                                            ...config,
                                            timeouts: {
                                                ...config.timeouts,
                                                generation: {...config.timeouts.generation, [level]: parseInt(e.target.value)}
                                            }
                                        })}
                                     />
                                 </div>
                             </div>
                         </div>
                     ))}
                </CardContent>
            </Card>
            
            <Card>
                <CardHeader><CardTitle>重试策略</CardTitle></CardHeader>
                <CardContent className="space-y-6">
                    <div className="flex items-center justify-between border-b pb-4">
                        <div className="space-y-0.5">
                            <Label>空响应重试 (Retry on Empty)</Label>
                            <p className="text-xs text-muted-foreground">当上游返回空内容时触发重试</p>
                        </div>
                        <Switch
                            checked={config.retries.conditions.retry_on_empty}
                            onCheckedChange={(c) => setConfig({
                                ...config,
                                retries: {
                                    ...config.retries,
                                    conditions: {
                                        ...config.retries.conditions,
                                        retry_on_empty: c
                                    }
                                }
                            })}
                        />
                    </div>

                    <div className="space-y-2">
                        <Label>状态码 (Status Codes)</Label>
                        <div className="flex flex-wrap gap-2">
                            {config.retries.conditions.status_codes.map((code, i) => (
                                <Badge key={i} variant="secondary" className="gap-2">
                                    {code}
                                    <span className="cursor-pointer hover:text-red-500" onClick={() => {
                                        const newCodes = [...config.retries.conditions.status_codes];
                                        newCodes.splice(i, 1);
                                        setConfig({...config, retries: {...config.retries, conditions: {...config.retries.conditions, status_codes: newCodes}}});
                                    }}>×</span>
                                </Badge>
                            ))}
                            <Button variant="ghost" size="sm" onClick={() => {
                                const code = prompt("输入状态码:");
                                if(code) {
                                    setConfig({...config, retries: {...config.retries, conditions: {...config.retries.conditions, status_codes: [...config.retries.conditions.status_codes, parseInt(code)]}}});
                                }
                            }}>+</Button>
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label>错误关键词 (Error Keywords)</Label>
                        <div className="flex flex-wrap gap-2">
                            {config.retries.conditions.error_keywords.map((kw, i) => (
                                <Badge key={i} variant="outline" className="gap-2">
                                    {kw}
                                    <span className="cursor-pointer hover:text-red-500" onClick={() => {
                                        const newKw = [...config.retries.conditions.error_keywords];
                                        newKw.splice(i, 1);
                                        setConfig({...config, retries: {...config.retries, conditions: {...config.retries.conditions, error_keywords: newKw}}});
                                    }}>×</span>
                                </Badge>
                            ))}
                            <Button variant="ghost" size="sm" onClick={() => {
                                const kw = prompt("输入错误关键词:");
                                if(kw) {
                                    setConfig({...config, retries: {...config.retries, conditions: {...config.retries.conditions, error_keywords: [...config.retries.conditions.error_keywords, kw]}}});
                                }
                            }}>+</Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>健康检查 (Health Check)</CardTitle>
                    <CardDescription>配置模型健康分数的自动恢复机制</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label>健康恢复速率 (Decay Rate)</Label>
                        <div className="flex items-center gap-4">
                            <Input 
                                type="number"
                                step="0.01"
                                min="0"
                                value={config.health.decay_rate}
                                onChange={(e) => setConfig({
                                    ...config,
                                    health: {
                                        ...config.health,
                                        decay_rate: parseFloat(e.target.value)
                                    }
                                })}
                                className="w-32"
                            />
                            <span className="text-sm text-muted-foreground">点/分钟 (Points/Min)</span>
                        </div>
                        <p className="text-xs text-muted-foreground">模型发生故障后，故障分数会随时间自动减少，从而恢复健康度。</p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}

function RouterSettings({ config, setConfig }: { config: AppConfig, setConfig: any }) {
    return (
        <Card>
            <CardHeader><CardTitle>意图路由配置</CardTitle></CardHeader>
            <CardContent className="space-y-4">
                <div className="flex items-center gap-2">
                    <Switch 
                        checked={config.router.enabled}
                        onCheckedChange={(c) => setConfig({...config, router: {...config.router, enabled: c}})}
                    />
                    <Label>启用 LLM 路由</Label>
                </div>
                <p className="text-sm text-muted-foreground">
                    关闭意图路由后，系统将仅使用 <strong>T1 层级</strong> 模型，并启用故障重试模式 (适用于纯容灾场景)。
                </p>
                {config.router.enabled && (
                    <>
                        <div className="grid gap-2">
                            <Label>路由模型</Label>
                            <Input 
                                value={config.router.model}
                                onChange={(e) => setConfig({...config, router: {...config.router, model: e.target.value}})}
                            />
                        </div>
                        <div className="grid gap-2">
                            <Label>Prompt 模板</Label>
                            <Textarea 
                                className="h-32 font-mono text-xs"
                                value={config.router.prompt_template}
                                onChange={(e) => setConfig({...config, router: {...config.router, prompt_template: e.target.value}})}
                            />
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    )
}

function ParamSettings({ config, setConfig }: { config: AppConfig, setConfig: any }) {
    return (
        <div className="space-y-6">
            <Card>
                <CardHeader><CardTitle>全局参数</CardTitle></CardHeader>
                <CardContent>
                    <JsonEditor 
                        value={config.params.global_params}
                        onChange={(v) => setConfig({...config, params: {...config.params, global_params: v}})}
                    />
                </CardContent>
            </Card>
             <Card>
                <CardHeader><CardTitle>模型特定参数</CardTitle></CardHeader>
                <CardContent>
                    <JsonEditor 
                        value={config.params.model_params}
                        onChange={(v) => setConfig({...config, params: {...config.params, model_params: v}})}
                    />
                </CardContent>
            </Card>
        </div>
    )
}

function SecuritySettings({ has2FA, checkAuth }: any) {
    return (
        <Card>
            <CardHeader><CardTitle>账户安全</CardTitle></CardHeader>
            <CardContent className="space-y-4">
                <div className="flex justify-between items-center border p-4 rounded">
                    <div>
                        <div className="font-medium">修改用户名</div>
                        <div className="text-sm text-muted-foreground">修改当前登录用户名</div>
                    </div>
                    <Dialog>
                        <DialogTrigger asChild><Button variant="outline">修改</Button></DialogTrigger>
                        <DialogContent><ChangeUsername /></DialogContent>
                    </Dialog>
                </div>

                <div className="flex justify-between items-center border p-4 rounded">
                    <div>
                        <div className="font-medium">修改密码</div>
                        <div className="text-sm text-muted-foreground">定期修改密码</div>
                    </div>
                    <Dialog>
                        <DialogTrigger asChild><Button variant="outline">修改</Button></DialogTrigger>
                        <DialogContent><ChangePassword /></DialogContent>
                    </Dialog>
                </div>
                 <div className="flex justify-between items-center border p-4 rounded">
                    <div>
                        <div className="font-medium">两步验证 (2FA)</div>
                        <div className="text-sm text-muted-foreground">{has2FA ? "已启用" : "未启用"}</div>
                    </div>
                    {has2FA ? <Button disabled>已启用</Button> : (
                         <Dialog>
                            <DialogTrigger asChild><Button>启用</Button></DialogTrigger>
                            <DialogContent><Setup2FA onComplete={checkAuth}/></DialogContent>
                        </Dialog>
                    )}
                </div>
            </CardContent>
        </Card>
    )
}

function HistoryDialog({ onRollback }: { onRollback: () => void }) {
    const [history, setHistory] = useState<ConfigHistory[]>([]);
    const [open, setOpen] = useState(false);

    useEffect(() => {
        if(open) {
            fetchHistory().then(setHistory);
        }
    }, [open]);

    const handleRollback = async (id: number) => {
        if(confirm("确定要回滚到此版本配置吗？")) {
            try {
                await rollbackConfig(id);
                toast.success("回滚成功");
                setOpen(false);
                onRollback();
            } catch(e) {
                toast.error("回滚失败");
            }
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" className="gap-2"><HistoryIcon className="h-4 w-4"/> 历史记录</Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl">
                <DialogHeader>
                    <DialogTitle>配置变更历史</DialogTitle>
                </DialogHeader>
                <ScrollArea className="h-[400px]">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>时间</TableHead>
                                <TableHead>用户</TableHead>
                                <TableHead>变更原因</TableHead>
                                <TableHead>操作</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {history.map((h) => (
                                <TableRow key={h.id}>
                                    <TableCell>{new Date(h.timestamp + "Z").toLocaleString()}</TableCell>
                                    <TableCell>{h.user}</TableCell>
                                    <TableCell>{h.change_reason}</TableCell>
                                    <TableCell>
                                        <Button size="sm" variant="ghost" onClick={() => handleRollback(h.id)}>
                                            <RotateCcw className="h-4 w-4 mr-1"/> 回滚
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </ScrollArea>
            </DialogContent>
        </Dialog>
    )
}

function JsonEditor({ value, onChange }: { value: any, onChange: (val: any) => void }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));

  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
  }, [value]);

  return (
    <Textarea 
      className="font-mono text-xs h-40"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
         try {
           const val = JSON.parse(text);
           onChange(val);
         } catch (e) {
           toast.error("JSON 格式错误");
         }
      }}
    />
  );
}
