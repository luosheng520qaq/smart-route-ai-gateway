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
import { Save, Plus, Trash2, GripVertical, Brain, AlertOctagon } from 'lucide-react';
import { AppConfig, fetchConfig, updateConfig } from '@/lib/api';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function ConfigPage() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);

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
      toast.error("配置保存失败");
    }
  };

  const updateModelList = (level: 't1' | 't2' | 't3', index: number, value: string) => {
    if (!config) return;
    const newList = [...(level === 't1' ? config.t1_models : level === 't2' ? config.t2_models : config.t3_models)];
    newList[index] = value;
    setConfig({
      ...config,
      [level === 't1' ? 't1_models' : level === 't2' ? 't2_models' : 't3_models']: newList
    });
  };

  const addModel = (level: 't1' | 't2' | 't3') => {
    if (!config) return;
    const newList = [...(level === 't1' ? config.t1_models : level === 't2' ? config.t2_models : config.t3_models)];
    newList.push("");
    setConfig({
      ...config,
      [level === 't1' ? 't1_models' : level === 't2' ? 't2_models' : 't3_models']: newList
    });
  };

  const removeModel = (level: 't1' | 't2' | 't3', index: number) => {
    if (!config) return;
    const newList = [...(level === 't1' ? config.t1_models : level === 't2' ? config.t2_models : config.t3_models)];
    newList.splice(index, 1);
    setConfig({
      ...config,
      [level === 't1' ? 't1_models' : level === 't2' ? 't2_models' : 't3_models']: newList
    });
  };

  const updateTimeout = (level: 't1' | 't2' | 't3', value: number[]) => {
    if (!config) return;
    setConfig({
      ...config,
      timeouts: {
        ...config.timeouts,
        [level]: value[0]
      }
    });
  };

  const updateStreamTimeout = (level: 't1' | 't2' | 't3', value: number[]) => {
    if (!config) return;
    setConfig({
      ...config,
      stream_timeouts: {
        ...(config.stream_timeouts || { "t1": 300000, "t2": 300000, "t3": 300000 }),
        [level]: value[0]
      }
    });
  };

  const updateRetryRounds = (level: 't1' | 't2' | 't3', value: number[]) => {
    if (!config) return;
    setConfig({
      ...config,
      retry_rounds: {
        ...(config.retry_rounds || { "t1": 1, "t2": 1, "t3": 1 }),
        [level]: value[0]
      }
    });
  };

  const addStatusCode = () => {
    if (!config) return;
    setConfig({
      ...config,
      retry_config: {
        ...config.retry_config,
        status_codes: [...config.retry_config.status_codes, 0]
      }
    });
  };

  const updateStatusCode = (index: number, value: string) => {
    if (!config) return;
    const newCodes = [...config.retry_config.status_codes];
    newCodes[index] = parseInt(value) || 0;
    setConfig({
      ...config,
      retry_config: {
        ...config.retry_config,
        status_codes: newCodes
      }
    });
  };

  const removeStatusCode = (index: number) => {
    if (!config) return;
    const newCodes = [...config.retry_config.status_codes];
    newCodes.splice(index, 1);
    setConfig({
      ...config,
      retry_config: {
        ...config.retry_config,
        status_codes: newCodes
      }
    });
  };

  const addErrorKeyword = () => {
    if (!config) return;
    setConfig({
      ...config,
      retry_config: {
        ...config.retry_config,
        error_keywords: [...config.retry_config.error_keywords, ""]
      }
    });
  };

  const updateErrorKeyword = (index: number, value: string) => {
    if (!config) return;
    const newKeywords = [...config.retry_config.error_keywords];
    newKeywords[index] = value;
    setConfig({
      ...config,
      retry_config: {
        ...config.retry_config,
        error_keywords: newKeywords
      }
    });
  };

  const removeErrorKeyword = (index: number) => {
    if (!config) return;
    const newKeywords = [...config.retry_config.error_keywords];
    newKeywords.splice(index, 1);
    setConfig({
      ...config,
      retry_config: {
        ...config.retry_config,
        error_keywords: newKeywords
      }
    });
  };


  if (loading || !config) return <div>加载配置中...</div>;

  return (
    <div className="space-y-6 max-w-4xl mx-auto animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 md:gap-0">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">系统配置</h2>
          <p className="text-muted-foreground">管理路由策略和上游供应商设置。</p>
        </div>
        <Button onClick={handleSave} className="gap-2">
          <Save className="h-4 w-4" /> 保存更改
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>上游供应商 (Upstream Provider)</CardTitle>
          <CardDescription>配置全局 LLM 供应商 (例如 OpenAI, DeepSeek, Azure)。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4">
            <div className="space-y-2">
              <Label>Base URL (API 地址)</Label>
              <Input 
                value={config.upstream_base_url} 
                onChange={(e) => setConfig({...config, upstream_base_url: e.target.value})} 
                placeholder="https://api.openai.com/v1" 
              />
            </div>
            <div className="space-y-2">
              <Label>API Key (密钥)</Label>
              <Input 
                type="password"
                value={config.upstream_api_key} 
                onChange={(e) => setConfig({...config, upstream_api_key: e.target.value})} 
                placeholder="sk-..." 
              />
            </div>
            <div className="space-y-2">
              <Label>Gateway API Key (网关访问密钥)</Label>
              <Input 
                type="password"
                value={config.gateway_api_key || ""} 
                onChange={(e) => setConfig({...config, gateway_api_key: e.target.value})} 
                placeholder="留空则允许任意 Key 访问" 
              />
              <p className="text-sm text-muted-foreground">设置此 Key 后，客户端请求必须携带相同的 Bearer Token 才能通过验证。</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>多供应商配置 (Multi-Provider)</CardTitle>
          <CardDescription>配置额外的模型供应商。如果在此处定义了 Provider，可以在模型 ID 中使用 `provider_id/model_name` 来指定。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Provider List Editor */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <Label>供应商列表 (Providers)</Label>
              <Button variant="outline" size="sm" onClick={() => {
                if (!config) return;
                const newId = `provider_${Object.keys(config.providers || {}).length + 1}`;
                setConfig({
                  ...config,
                  providers: {
                    ...(config.providers || {}),
                    [newId]: { base_url: "", api_key: "" }
                  }
                });
              }}>
                <Plus className="h-4 w-4 mr-1" /> 添加供应商
              </Button>
            </div>
            
            <div className="space-y-4">
              {Object.entries(config.providers || {}).map(([id, provider]) => (
                <div key={id} className="border p-4 rounded-lg space-y-3 relative">
                  <div className="absolute top-2 right-2">
                    <Button variant="ghost" size="icon" onClick={() => {
                       if (!config) return;
                       const newProviders = { ...config.providers };
                       delete newProviders[id];
                       setConfig({ ...config, providers: newProviders });
                    }}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                     <div className="space-y-2">
                      <Label>Provider ID</Label>
                      <Input 
                        value={id}
                        onChange={(e) => {
                          if (!config) return;
                          const newId = e.target.value;
                          if (newId === id || !newId) return;
                          
                          const newProviders = { ...config.providers };
                          newProviders[newId] = newProviders[id];
                          delete newProviders[id];
                          setConfig({ ...config, providers: newProviders });
                        }}
                        placeholder="e.g. azure"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                       <Label>Base URL</Label>
                       <Input 
                         value={provider.base_url}
                         onChange={(e) => {
                           if (!config) return;
                           setConfig({
                             ...config,
                             providers: {
                               ...config.providers,
                               [id]: { ...provider, base_url: e.target.value }
                             }
                           });
                         }}
                         placeholder="https://..."
                       />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>API Key</Label>
                    <Input 
                      type="password"
                      value={provider.api_key}
                      onChange={(e) => {
                        if (!config) return;
                         setConfig({
                             ...config,
                             providers: {
                               ...config.providers,
                               [id]: { ...provider, api_key: e.target.value }
                             }
                           });
                      }}
                      placeholder="sk-..."
                    />
                  </div>
                </div>
              ))}
              {Object.keys(config.providers || {}).length === 0 && (
                <div className="text-center text-sm text-muted-foreground py-4">
                  暂无额外供应商，点击上方按钮添加。
                </div>
              )}
            </div>
          </div>

           {/* Model Map Editor */}
           <div className="space-y-4 border-t pt-4">
            <div className="flex justify-between items-center">
              <Label>模型映射 (Model Mapping)</Label>
               <Button variant="outline" size="sm" onClick={() => {
                if (!config) return;
                setConfig({
                  ...config,
                  model_provider_map: {
                    ...(config.model_provider_map || {}),
                    "": ""
                  }
                });
              }}>
                <Plus className="h-4 w-4 mr-1" /> 添加映射
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">将特定模型 ID 自动路由到指定供应商（无需在 T1/T2/T3 列表加前缀）。</p>
            
            <div className="space-y-2">
              {Object.entries(config.model_provider_map || {}).map(([model, providerId], index) => (
                <div key={index} className="flex items-center gap-2">
                  <Input 
                    className="flex-1"
                    value={model}
                    onChange={(e) => {
                       if (!config) return;
                       const newMap = { ...config.model_provider_map };
                       const newVal = newMap[model];
                       delete newMap[model];
                       newMap[e.target.value] = newVal;
                       setConfig({ ...config, model_provider_map: newMap });
                    }}
                    placeholder="模型 ID (如 gpt-4)"
                  />
                  <span className="text-muted-foreground">→</span>
                  <select 
                    className="flex-1 h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    value={providerId}
                    onChange={(e) => {
                       if (!config) return;
                       setConfig({
                         ...config,
                         model_provider_map: {
                           ...config.model_provider_map,
                           [model]: e.target.value
                         }
                       });
                    }}
                  >
                    <option value="" disabled>选择供应商</option>
                    {Object.keys(config.providers || {}).map(pid => (
                      <option key={pid} value={pid}>{pid}</option>
                    ))}
                  </select>
                   <Button variant="ghost" size="icon" onClick={() => {
                       if (!config) return;
                       const newMap = { ...config.model_provider_map };
                       delete newMap[model];
                       setConfig({ ...config, model_provider_map: newMap });
                    }}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>默认参数配置 (Default Parameters)</CardTitle>
          <CardDescription>配置全局和特定模型的默认参数 (如 temperature, top_p)。这有助于适配对参数有特殊要求的上游模型 (如 Kimi)。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
           {/* Global Params */}
           <div className="space-y-4">
            <div className="flex justify-between items-center">
               <Label>全局参数 (Global Params)</Label>
               <Button variant="outline" size="sm" onClick={() => {
                 if (!config) return;
                 setConfig({
                   ...config,
                   global_params: { ...(config.global_params || {}), "new_param": 0.7 }
                 });
               }}>
                 <Plus className="h-4 w-4 mr-1" /> 添加参数
               </Button>
            </div>
            
            <div className="space-y-2">
               {Object.entries(config.global_params || {}).map(([key, value], index) => (
                 <div key={index} className="flex items-center gap-2">
                    <Input 
                      className="w-1/3"
                      value={key}
                      onChange={(e) => {
                         if (!config) return;
                         const newParams = { ...config.global_params };
                         const val = newParams[key];
                         delete newParams[key];
                         newParams[e.target.value] = val;
                         setConfig({ ...config, global_params: newParams });
                      }}
                      placeholder="参数名 (如 temperature)"
                    />
                    <Input 
                      className="flex-1"
                      value={typeof value === 'object' ? JSON.stringify(value) : value}
                      onChange={(e) => {
                         if (!config) return;
                         setConfig({
                           ...config,
                           global_params: { ...config.global_params, [key]: e.target.value }
                         });
                      }}
                      onBlur={(e) => {
                         if (!config) return;
                         let val: any = e.target.value;
                         // Try to parse number or boolean
                         if (!isNaN(Number(val)) && val.trim() !== '') val = Number(val);
                         if (val === 'true') val = true;
                         if (val === 'false') val = false;
                         
                         setConfig({
                           ...config,
                           global_params: { ...config.global_params, [key]: val }
                         });
                      }}
                      placeholder="值"
                    />
                     <Button variant="ghost" size="icon" onClick={() => {
                         if (!config) return;
                         const newParams = { ...config.global_params };
                         delete newParams[key];
                         setConfig({ ...config, global_params: newParams });
                      }}>
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                 </div>
               ))}
               {Object.keys(config.global_params || {}).length === 0 && (
                 <p className="text-sm text-muted-foreground">暂无全局参数。</p>
               )}
            </div>
          </div>

          {/* Model Specific Params */}
          <div className="space-y-4 border-t pt-4">
             <div className="flex justify-between items-center">
               <Label>特定模型参数 (Model Specific Params)</Label>
                <Button variant="outline" size="sm" onClick={() => {
                 if (!config) return;
                 setConfig({
                   ...config,
                   model_params: {
                     ...(config.model_params || {}),
                     "model_id": { "param": "value" }
                   }
                 });
               }}>
                 <Plus className="h-4 w-4 mr-1" /> 添加模型配置
               </Button>
            </div>
            
             <div className="space-y-4">
               {Object.entries(config.model_params || {}).map(([modelId, params]) => (
                 <div key={modelId} className="border p-4 rounded-lg space-y-3 relative">
                    <div className="absolute top-2 right-2">
                      <Button variant="ghost" size="icon" onClick={() => {
                         if (!config) return;
                         const newModelParams = { ...config.model_params };
                         delete newModelParams[modelId];
                         setConfig({ ...config, model_params: newModelParams });
                      }}>
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>

                    <div className="space-y-2">
                      <Label>模型 ID</Label>
                      <Input 
                        value={modelId}
                        onChange={(e) => {
                           if (!config) return;
                           const newId = e.target.value;
                           if (newId === modelId || !newId) return;
                           
                           const newModelParams = { ...config.model_params };
                           newModelParams[newId] = newModelParams[modelId];
                           delete newModelParams[modelId];
                           setConfig({ ...config, model_params: newModelParams });
                        }}
                        placeholder="e.g. kimik2.5"
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>参数列表 (JSON)</Label>
                      <JsonEditor 
                        value={params}
                        onChange={(val) => {
                           if (!config) return;
                           setConfig({
                             ...config,
                             model_params: { ...config.model_params, [modelId]: val }
                           });
                        }}
                      />
                      <p className="text-xs text-muted-foreground">此处保持 JSON 编辑以支持复杂结构。</p>
                    </div>
                 </div>
               ))}
                {Object.keys(config.model_params || {}).length === 0 && (
                 <div className="text-center text-sm text-muted-foreground py-4">
                   暂无特定模型配置。
                 </div>
               )}
             </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            <CardTitle>意图分类模型 (Intent Router)</CardTitle>
          </div>
          <CardDescription>使用额外的轻量级模型来分析用户意图复杂度 (T1/T2/T3)，而非仅依赖关键词。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center space-x-2">
            <Switch 
              id="router-enabled" 
              checked={config.router_config.enabled} 
              onCheckedChange={(checked) => setConfig({...config, router_config: {...config.router_config, enabled: checked}})}
            />
            <Label htmlFor="router-enabled">
              启用 LLM 意图分析
              {!config.router_config.enabled && <span className="text-xs text-muted-foreground ml-2">(已关闭：将随机分发到 T1/T2/T3)</span>}
            </Label>
          </div>
          
          {config.router_config.enabled && (
            <div className="space-y-4 mt-4 pl-4 border-l-2 border-primary/20">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>分类模型 ID</Label>
                  <Input 
                    value={config.router_config.model} 
                    onChange={(e) => setConfig({...config, router_config: {...config.router_config, model: e.target.value}})} 
                    placeholder="gpt-3.5-turbo" 
                  />
                </div>
                <div className="space-y-2">
                  <Label>API Key (若不同)</Label>
                  <Input 
                    type="password"
                    value={config.router_config.api_key} 
                    onChange={(e) => setConfig({...config, router_config: {...config.router_config, api_key: e.target.value}})} 
                    placeholder="sk-..." 
                  />
                </div>
              </div>
               <div className="space-y-2">
                  <Label>Base URL (若不同)</Label>
                  <Input 
                    value={config.router_config.base_url} 
                    onChange={(e) => setConfig({...config, router_config: {...config.router_config, base_url: e.target.value}})} 
                    placeholder="https://api.openai.com/v1" 
                  />
                </div>
              <div className="space-y-2">
                <Label>Prompt 模板</Label>
                <Textarea 
                  className="h-32 font-mono text-xs"
                  value={config.router_config.prompt_template} 
                  onChange={(e) => setConfig({...config, router_config: {...config.router_config, prompt_template: e.target.value}})} 
                />
                <p className="text-xs text-muted-foreground">使用 {"{history}"} 占位符代表最近的用户对话历史。</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
           <div className="flex items-center gap-2">
            <AlertOctagon className="h-5 w-5 text-orange-500" />
            <CardTitle>故障重试策略 (Failover Conditions)</CardTitle>
          </div>
          <CardDescription>当上游返回以下状态码或包含特定关键词时，自动切换到下一个模型。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
             <div className="flex justify-between items-center">
                <Label>触发重试的状态码 (Status Codes)</Label>
                <Button variant="outline" size="sm" onClick={addStatusCode}>
                  <Plus className="h-4 w-4 mr-1" /> 添加
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {config.retry_config.status_codes.map((code, index) => (
                  <div key={index} className="flex items-center gap-1">
                    <Input 
                      type="number"
                      className="w-20" 
                      value={code} 
                      onChange={(e) => updateStatusCode(index, e.target.value)}
                    />
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removeStatusCode(index)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                ))}
              </div>
          </div>

          <div className="space-y-2">
             <div className="flex justify-between items-center">
                <Label>触发重试的错误关键词 (Error Keywords)</Label>
                <Button variant="outline" size="sm" onClick={addErrorKeyword}>
                  <Plus className="h-4 w-4 mr-1" /> 添加
                </Button>
              </div>
              <div className="space-y-2">
                {config.retry_config.error_keywords.map((keyword, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input 
                      value={keyword} 
                      onChange={(e) => updateErrorKeyword(index, e.target.value)}
                      placeholder="e.g. rate limit"
                    />
                    <Button variant="ghost" size="icon" onClick={() => removeErrorKeyword(index)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                ))}
              </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="t1" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="t1">Level 1 (快速)</TabsTrigger>
          <TabsTrigger value="t2">Level 2 (智能)</TabsTrigger>
          <TabsTrigger value="t3">Level 3 (专家)</TabsTrigger>
        </TabsList>
        
        {['t1', 't2', 't3'].map((level) => (
          <TabsContent key={level} value={level}>
            <Card>
              <CardHeader>
                <CardTitle>{level.toUpperCase()} 路由策略</CardTitle>
                <CardDescription>
                  为 {level === 't1' ? '简单查询' : level === 't2' ? '通用任务' : '复杂推理'} 配置模型列表和超时时间。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                
                <div className="space-y-4">
                  <div className="flex justify-between">
                    <Label>首 Token 超时 (Time-to-First-Token)</Label>
                    <span className="text-sm text-muted-foreground">{config.timeouts[level]} ms</span>
                  </div>
                  <Slider 
                    value={[config.timeouts[level]]} 
                    max={60000} 
                    step={1000} 
                    onValueChange={(val) => updateTimeout(level as any, val)} 
                  />
                </div>

                <div className="space-y-2">
                   <Label>本层级路由策略 (Routing Strategy)</Label>
                   <Select 
                     value={config.routing_strategies?.[level] || "sequential"} 
                     onValueChange={(val) => setConfig({
                        ...config, 
                        routing_strategies: {
                            ...(config.routing_strategies || {t1: "sequential", t2: "sequential", t3: "sequential"}),
                            [level]: val
                        }
                     })}
                   >
                     <SelectTrigger>
                       <SelectValue placeholder="选择路由策略" />
                     </SelectTrigger>
                     <SelectContent>
                       <SelectItem value="sequential">顺序模式 (Sequential)</SelectItem>
                       <SelectItem value="random">随机模式 (Random)</SelectItem>
                       <SelectItem value="adaptive">自适应模式 (Adaptive)</SelectItem>
                     </SelectContent>
                   </Select>
                   <p className="text-xs text-muted-foreground">
                     顺序模式按列表优先；随机模式完全随机；自适应模式根据失败率调整权重。
                   </p>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between">
                    <Label>完整生成超时 (Total Generation Timeout)</Label>
                    <span className="text-sm text-muted-foreground">
                      {(config.stream_timeouts?.[level] ?? 300000) / 1000} s
                    </span>
                  </div>
                  <Slider 
                    value={[config.stream_timeouts?.[level] ?? 300000]} 
                    max={600000} 
                    step={5000} 
                    onValueChange={(val) => updateStreamTimeout(level as any, val)} 
                  />
                  <p className="text-xs text-muted-foreground">允许模型生成回复的最大时长。若超过此时间仍未完成，将强制断开并尝试下一个模型。</p>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between">
                    <Label>模型轮询轮次 (Retry Rounds)</Label>
                    <span className="text-sm text-muted-foreground">
                      {config.retry_rounds?.[level] ?? 1} 轮
                    </span>
                  </div>
                  <Slider 
                    value={[config.retry_rounds?.[level] ?? 1]} 
                    max={5} 
                    step={1} 
                    min={1}
                    onValueChange={(val) => updateRetryRounds(level as any, val)} 
                  />
                  <p className="text-xs text-muted-foreground">当所有模型都失败时，重新从头开始尝试的次数。</p>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <Label>模型优先级列表 (按顺序尝试)</Label>
                    <Button variant="outline" size="sm" onClick={() => addModel(level as any)}>
                      <Plus className="h-4 w-4 mr-1" /> 添加模型
                    </Button>
                  </div>
                  <div className="space-y-2 mt-2">
                    {(level === 't1' ? config.t1_models : level === 't2' ? config.t2_models : config.t3_models).map((model, index) => (
                      <div key={index} className="flex items-center gap-2">
                        <GripVertical className="h-4 w-4 text-muted-foreground cursor-grab" />
                        <Input 
                          value={model} 
                          onChange={(e) => updateModelList(level as any, index, e.target.value)}
                          placeholder="模型 ID (例如 gpt-3.5-turbo)"
                        />
                        <Button variant="ghost" size="icon" onClick={() => removeModel(level as any, index)}>
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>

              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

function JsonEditor({ value, onChange }: { value: any, onChange: (val: any) => void }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));

  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
  }, [value]);

  return (
    <Textarea 
      className="font-mono text-xs h-20"
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
