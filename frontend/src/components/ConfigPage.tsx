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
      <div className="flex justify-between items-center">
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
        <CardContent className="space-y-4">
            <div className="space-y-2">
            <Label>供应商列表 (Providers JSON)</Label>
            <Textarea 
              className="font-mono text-sm h-48"
              value={JSON.stringify(config.providers || {}, null, 2)} 
              onChange={(e) => {
                try {
                   const val = JSON.parse(e.target.value);
                   setConfig({...config, providers: val});
                } catch (e) {
                }
              }} 
              placeholder='{
  "azure": { 
    "base_url": "https://resource.openai.azure.com/...", 
    "api_key": "..." 
  },
  "deepseek": { 
    "base_url": "https://api.deepseek.com", 
    "api_key": "..." 
  }
}'
            />
             <p className="text-xs text-muted-foreground">
               JSON 格式。Key 为 Provider ID (如 "azure")，Value 包含 base_url 和 api_key。<br/>
               配置后，可在 T1/T2/T3 列表中使用 <code>azure/gpt-4</code> 的形式来指定使用该供应商。
             </p>
          </div>

           <div className="space-y-2">
            <Label>模型映射 (Model Map JSON)</Label>
            <Textarea 
              className="font-mono text-sm h-24"
              value={JSON.stringify(config.model_provider_map || {}, null, 2)} 
              onChange={(e) => {
                try {
                   const val = JSON.parse(e.target.value);
                   setConfig({...config, model_provider_map: val});
                } catch (e) {
                }
              }} 
              placeholder='{
  "gpt-4": "azure",
  "claude-3-opus": "anthropic"
}'
            />
             <p className="text-xs text-muted-foreground">
               可选。将特定模型 ID 自动映射到供应商 ID。如果使用了 `provider/model` 格式，则忽略此映射。
             </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>默认参数配置 (Default Parameters)</CardTitle>
          <CardDescription>配置全局和特定模型的默认参数 (如 temperature, top_p)。这有助于适配对参数有特殊要求的上游模型 (如 Kimi)。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
           <div className="space-y-2">
            <Label>全局参数 (Global Params JSON)</Label>
            <Textarea 
              className="font-mono text-sm h-24"
              value={JSON.stringify(config.global_params || {}, null, 2)} 
              onChange={(e) => {
                try {
                  const val = JSON.parse(e.target.value);
                  setConfig({...config, global_params: val});
                } catch (e) {
                   // Allow editing invalid JSON temporarily or handle error state if desired
                   // For simplicity in this text-based tool, we might not have complex validation UI
                }
              }} 
              placeholder='{"temperature": 0.7}'
            />
            <p className="text-xs text-muted-foreground">JSON 格式。这些参数将作为默认值应用于所有请求，除非请求中已指定。</p>
          </div>

          <div className="space-y-2">
            <Label>特定模型参数 (Model Specific Params JSON)</Label>
             <Textarea 
              className="font-mono text-sm h-48"
              value={JSON.stringify(config.model_params || {}, null, 2)} 
              onChange={(e) => {
                try {
                   const val = JSON.parse(e.target.value);
                   setConfig({...config, model_params: val});
                } catch (e) {
                }
              }} 
              placeholder='{
  "gpt-4": { "top_p": 0.5 },
  "kimik2.5": { "top_p": 0.95 }
}'
            />
             <p className="text-xs text-muted-foreground">JSON 格式。Key 为模型 ID，Value 为参数对象。优先级高于全局参数。</p>
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
            <Label htmlFor="router-enabled">启用 LLM 意图分析</Label>
          </div>
          
          {config.router_config.enabled && (
            <div className="space-y-4 mt-4 pl-4 border-l-2 border-primary/20">
              <div className="grid grid-cols-2 gap-4">
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
                    <Label>超时阈值 (毫秒)</Label>
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
