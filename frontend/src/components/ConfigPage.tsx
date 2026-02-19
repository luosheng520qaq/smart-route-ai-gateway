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
import { AppConfig, fetchConfig, updateConfig, fetchHistory, rollbackConfig, ConfigHistory, api } from '@/lib/api';
import { Setup2FA } from './AuthPage';
import { ChangePassword } from './ChangePassword';
import { ChangeUsername } from './ChangeUsername';
import { useAuth } from '@/lib/auth';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription, DialogFooter } from "@/components/ui/dialog";
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

function BatchAddDialog({ onAdd }: { onAdd: (models: string[]) => void }) {
    const [text, setText] = useState("");
    const [open, setOpen] = useState(false);

    const handleConfirm = () => {
        const models = text.split('\n').map(s => s.trim()).filter(s => s);
        if (models.length > 0) {
            onAdd(models);
            setText("");
            setOpen(false);
            toast.success(`已添加 ${models.length} 个模型`);
        } else {
             toast.warning("请输入模型名称");
        }
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                    <Plus className="h-4 w-4 mr-1"/> 批量添加
                </Button>
            </DialogTrigger>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>批量添加模型</DialogTitle>
                    <DialogDescription>每行输入一个模型名称，点击确定保存。</DialogDescription>
                </DialogHeader>
                <Textarea 
                    value={text} 
                    onChange={e => setText(e.target.value)} 
                    placeholder={"gpt-4\ngpt-3.5-turbo\n..."}
                    className="h-[300px] font-mono"
                />
                <DialogFooter>
                    <Button onClick={handleConfirm}>确定</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

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
    const updateList = (level: 't1' | 't2' | 't3', list: any[]) => {
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
                                {config.models[level as 't1'|'t2'|'t3'].map((item, idx) => {
                                    // Normalize to consistent format
                                    let modelName: string;
                                    let providerId: string;
                                    if (typeof item === 'string') {
                                        if (item.includes('/')) {
                                            const parts = item.split('/');
                                            providerId = parts[0];
                                            modelName = parts[1];
                                        } else {
                                            providerId = 'upstream';
                                            modelName = item;
                                        }
                                    } else {
                                        modelName = item.model;
                                        providerId = item.provider;
                                    }
                                    
                                    const providerOptions = ['upstream', ...Object.keys(config.providers.custom || {})];
                                    
                                    return (
                                        <div key={idx} className="flex gap-2 items-center">
                                            <Select 
                                                value={providerId} 
                                                onValueChange={(val) => {
                                                    const newList = [...config.models[level as 't1'|'t2'|'t3']];
                                                    newList[idx] = { model: modelName, provider: val };
                                                    updateList(level as any, newList);
                                                }}
                                            >
                                                <SelectTrigger className="w-[140px]">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {providerOptions.map(p => (
                                                        <SelectItem key={p} value={p}>{p}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Input 
                                                className="flex-1"
                                                value={modelName}
                                                onChange={(e) => {
                                                    const newList = [...config.models[level as 't1'|'t2'|'t3']];
                                                    newList[idx] = { model: e.target.value, provider: providerId };
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
                                    );
                                })}
                                <div className="flex gap-2">
                                    <Button variant="outline" size="sm" onClick={() => {
                                        const newList = [...config.models[level as 't1'|'t2'|'t3'], { model: "", provider: "upstream" }];
                                        updateList(level as any, newList);
                                    }}>
                                        <Plus className="h-4 w-4 mr-1"/> 添加模型
                                    </Button>
                                    <BatchAddDialog onAdd={(models) => {
                                        const newList = [...config.models[level as 't1'|'t2'|'t3'], ...models.map(m => ({ model: m, provider: "upstream" }))];
                                        updateList(level as any, newList);
                                    }} />
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            ))}
        </Tabs>
    )
}

function ProviderSettings({ config, setConfig }: { config: AppConfig, setConfig: any }) {
    const providers = config.providers.custom || {};
    const providerIds = Object.keys(providers);
    const [selectedId, setSelectedId] = useState<string>(providerIds.length > 0 ? providerIds[0] : "");

    useEffect(() => {
        if (selectedId && !providers[selectedId] && providerIds.length > 0) {
            setSelectedId(providerIds[0]);
        } else if (!selectedId && providerIds.length > 0) {
            setSelectedId(providerIds[0]);
        }
    }, [providerIds.join(",")]);

    const handleAddProvider = () => {
         const id = prompt("输入 Provider ID (如 azure):");
         if(id) {
             if (providers[id]) {
                 toast.error("Provider ID 已存在");
                 return;
             }
             setConfig({
                 ...config,
                 providers: {
                     ...config.providers,
                     custom: {
                         ...config.providers.custom,
                         [id]: {base_url: "", api_key: "", protocol: "openai"}
                     }
                 }
             });
             setSelectedId(id);
         }
    };

    const handleDeleteProvider = (id: string) => {
        const newCustom = {...config.providers.custom};
        delete newCustom[id];
        setConfig({...config, providers: {...config.providers, custom: newCustom}});
    };

    const currentProvider = providers[selectedId];

    return (
        <div className="space-y-6">
            <Card>
                <CardHeader>
                    <CardTitle>默认上游 (Upstream)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid gap-2">
                        <Label>协议类型 (Protocol)</Label>
                        <Select 
                            value={config.providers.upstream.protocol || "openai"} 
                            onValueChange={(val) => setConfig({
                                ...config,
                                providers: {
                                    ...config.providers,
                                    upstream: {...config.providers.upstream, protocol: val}
                                }
                            })}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="openai">Standard (v1/chat/completions)</SelectItem>
                                <SelectItem value="v1-messages">Messages (v1/messages + No Stream)</SelectItem>
                                <SelectItem value="v1-response">Responses (v1/responses + No Stream)</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
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
                    <div className="flex items-center gap-2">
                        <Switch 
                            checked={config.providers.upstream.verify_ssl !== false}
                            onCheckedChange={(c) => setConfig({...config, providers: {...config.providers, upstream: {...config.providers.upstream, verify_ssl: c}}})}
                        />
                        <Label>验证 SSL 证书</Label>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle>自定义供应商 (Custom Providers)</CardTitle>
                    <div className="flex items-center gap-2">
                         {providerIds.length > 0 && (
                             <Select value={selectedId} onValueChange={setSelectedId}>
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue placeholder="选择供应商" />
                                </SelectTrigger>
                                <SelectContent>
                                    {providerIds.map(id => (
                                        <SelectItem key={id} value={id}>{id}</SelectItem>
                                    ))}
                                </SelectContent>
                             </Select>
                         )}
                         <Button variant="outline" size="icon" onClick={handleAddProvider}>
                            <Plus className="h-4 w-4"/>
                         </Button>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4 pt-4">
                    {currentProvider ? (
                        <div className="space-y-4 border p-4 rounded relative">
                            <Button variant="ghost" size="icon" className="absolute top-2 right-2" onClick={() => handleDeleteProvider(selectedId)}>
                                <Trash2 className="h-4 w-4 text-red-500"/>
                            </Button>
                            <div className="grid gap-2">
                                <Label>Provider ID</Label>
                                <Input value={selectedId} disabled />
                            </div>
                            <div className="grid gap-2">
                                <Label>协议类型 (Protocol)</Label>
                                <Select 
                                    value={currentProvider.protocol || "openai"} 
                                    onValueChange={(val) => setConfig({
                                        ...config,
                                        providers: {
                                            ...config.providers,
                                            custom: {
                                                ...config.providers.custom,
                                                [selectedId]: {...currentProvider, protocol: val}
                                            }
                                        }
                                    })}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="openai">Standard (v1/chat/completions)</SelectItem>
                                        <SelectItem value="v1-messages">Messages (v1/messages + No Stream)</SelectItem>
                                        <SelectItem value="v1-response">Responses (v1/responses + No Stream)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="grid gap-2">
                                <Label>Base URL</Label>
                                <Input 
                                    value={currentProvider.base_url}
                                    onChange={(e) => setConfig({
                                        ...config,
                                        providers: {
                                            ...config.providers,
                                            custom: {
                                                ...config.providers.custom,
                                                [selectedId]: {...currentProvider, base_url: e.target.value}
                                            }
                                        }
                                    })}
                                />
                            </div>
                            <div className="grid gap-2">
                                <Label>API Key</Label>
                                <Input 
                                    type="password"
                                    value={currentProvider.api_key}
                                    onChange={(e) => setConfig({
                                        ...config,
                                        providers: {
                                            ...config.providers,
                                            custom: {
                                                ...config.providers.custom,
                                                [selectedId]: {...currentProvider, api_key: e.target.value}
                                            }
                                        }
                                    })}
                                />
                            </div>
                            <div className="flex items-center gap-2">
                                <Switch 
                                    checked={currentProvider.verify_ssl !== false}
                                    onCheckedChange={(c) => setConfig({
                                        ...config,
                                        providers: {
                                            ...config.providers,
                                            custom: {
                                                ...config.providers.custom,
                                                [selectedId]: {...currentProvider, verify_ssl: c}
                                            }
                                        }
                                    })}
                                />
                                <Label>验证 SSL 证书</Label>
                            </div>
                        </div>
                    ) : (
                        <div className="text-center text-muted-foreground py-8">
                             暂无自定义供应商，请点击右上角 + 号添加。
                        </div>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>模型-供应商 映射 (Model Provider Map)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                        将特定模型名称映射到指定的自定义供应商 (ID)。未映射的模型将使用默认上游。
                    </p>
                    <div className="space-y-2">
                         {Object.entries(config.providers.map || {}).map(([model, providerId]) => (
                             <div key={model} className="flex items-center gap-2 border p-2 rounded">
                                 <div className="flex-1 font-mono text-sm">{model}</div>
                                 <div className="text-muted-foreground">→</div>
                                 <div className="flex-1 font-mono text-sm">{providerId as string}</div>
                                 <Button variant="ghost" size="icon" onClick={() => {
                                     const newMap = {...config.providers.map};
                                     delete newMap[model];
                                     setConfig({...config, providers: {...config.providers, map: newMap}});
                                 }}>
                                     <Trash2 className="h-4 w-4 text-red-500"/>
                                 </Button>
                             </div>
                         ))}
                         <div className="flex items-center gap-2 pt-2">
                             <Button variant="outline" className="w-full" onClick={() => {
                                 const model = prompt("输入模型名称 (如 gpt-4-turbo):");
                                 if (!model) return;
                                 
                                 const pid = prompt("输入 Provider ID (如 azure):");
                                 if (!pid) return;
                                 
                                 // Verify provider exists (optional but good UX)
                                 if (pid !== "upstream" && !config.providers.custom[pid]) {
                                     if(!confirm(`Provider ID '${pid}' 不存在。确定要添加吗？`)) return;
                                 }

                                 setConfig({
                                     ...config,
                                     providers: {
                                         ...config.providers,
                                         map: {
                                             ...config.providers.map,
                                             [model]: pid
                                         }
                                     }
                                 });
                             }}>
                                 <Plus className="h-4 w-4 mr-2"/> 添加映射
                             </Button>
                         </div>
                    </div>
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
    const [testMessage, setTestMessage] = useState("你好，请帮我写一段Python代码");
    const [testResult, setTestResult] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    const handleTest = async () => {
        setLoading(true);
        setTestResult(null);
        try {
            const res = await api.post("/api/router/test", { message: testMessage });
            const data = res.data;
            setTestResult(data);
            if (data.level) {
                toast.success(`分类结果: ${data.level.toUpperCase()}`);
            }
        } catch (e: any) {
            console.error(e);
            const errorMsg = e.response?.data?.detail || String(e);
            toast.error("请求失败: " + errorMsg);
            setTestResult({ error: errorMsg });
        } finally {
            setLoading(false);
        }
    };

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

                        <div className="flex items-center justify-between border p-3 rounded-md">
                            <div className="space-y-0.5">
                                <Label>验证 SSL 证书 (Verify SSL)</Label>
                                <p className="text-xs text-muted-foreground">
                                    如果是自签名证书，请关闭此选项 (不推荐生产环境)
                                </p>
                            </div>
                            <Switch 
                                checked={config.router.verify_ssl !== false} // Default true
                                onCheckedChange={(c) => setConfig({...config, router: {...config.router, verify_ssl: c}})}
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label>Router Base URL (Optional)</Label>
                            <Input 
                                value={config.router.base_url || ""}
                                onChange={(e) => setConfig({...config, router: {...config.router, base_url: e.target.value}})}
                                placeholder={`留空则使用默认: ${config.providers.upstream.base_url || "Upstream URL"}`}
                            />
                             <p className="text-xs text-muted-foreground">
                                仅当路由模型需要独立 API 地址时填写，否则请留空。
                            </p>
                        </div>

                        <div className="grid gap-2">
                            <Label>Router API Key (Optional)</Label>
                            <Input 
                                type="password"
                                value={config.router.api_key || ""}
                                onChange={(e) => setConfig({...config, router: {...config.router, api_key: e.target.value}})}
                                placeholder="留空则使用默认 Upstream API Key"
                            />
                        </div>

                        <div className="flex items-center gap-2">
                            <Switch 
                                checked={config.router.verify_ssl !== false}
                                onCheckedChange={(c) => setConfig({...config, router: {...config.router, verify_ssl: c}})}
                            />
                            <Label>验证 SSL 证书 (Router)</Label>
                        </div>

                        <div className="grid gap-2">
                            <Label>Prompt 模板</Label>
                            <Textarea 
                                className="h-32 font-mono text-xs"
                                value={config.router.prompt_template}
                                onChange={(e) => setConfig({...config, router: {...config.router, prompt_template: e.target.value}})}
                            />
                        </div>

                        <div className="border-t pt-4 mt-4">
                            <Label className="mb-2 block">路由测试</Label>
                            <div className="flex gap-2">
                                <Input 
                                    value={testMessage}
                                    onChange={(e) => setTestMessage(e.target.value)}
                                    placeholder="输入测试文本..."
                                />
                                <Button onClick={handleTest} disabled={loading}>
                                    {loading ? "测试中..." : "测试"}
                                </Button>
                            </div>
                            {testResult && (
                                <div className="mt-2 p-2 bg-muted rounded text-sm font-mono">
                                    {testResult.error ? (
                                        <span className="text-red-500">Error: {testResult.error}</span>
                                    ) : (
                                        <div className="flex items-center gap-2">
                                            <span className="font-bold text-primary">Result: {testResult.level}</span>
                                            <span className="text-muted-foreground text-xs">({new Date().toLocaleTimeString()})</span>
                                        </div>
                                    )}
                                </div>
                            )}
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

function SecuritySettings({ config, setConfig, has2FA, checkAuth }: any) {
    return (
        <Card>
            <CardHeader><CardTitle>账户安全</CardTitle></CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-2 border p-4 rounded">
                    <Label>登录会话有效期 (分钟)</Label>
                    <div className="flex items-center gap-4">
                         <Input 
                            type="number"
                            min="1"
                            value={config.security?.access_token_expire_minutes || 1440}
                            onChange={(e) => setConfig({
                                ...config,
                                security: {
                                    ...(config.security || {}),
                                    access_token_expire_minutes: parseInt(e.target.value) || 60
                                }
                            })}
                            className="w-32"
                        />
                        <span className="text-sm text-muted-foreground">
                            {((config.security?.access_token_expire_minutes || 1440) / 60).toFixed(1)} 小时
                        </span>
                    </div>
                    <p className="text-xs text-muted-foreground">设置登录后 Token 的有效时长。修改后需要重新登录生效。</p>
                </div>

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
