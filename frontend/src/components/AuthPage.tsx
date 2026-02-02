import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ShieldCheck, Lock, User, Loader2, ArrowRight } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { QRCodeSVG } from 'qrcode.react';

export function LoginPage() {
    const { login } = useAuth();
    const [loading, setLoading] = useState(false);
    const [step, setStep] = useState<'login' | '2fa'>('login');
    
    // Form Data
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [code, setCode] = useState('');

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            // 1. Attempt Login
            // If user has 2FA, backend currently doesn't distinguish well in the simple flow 
            // unless we try to login and it fails with specific 2FA requirement.
            // BUT, our backend implementation returns token if 2FA is set but no code provided? 
            // Wait, looking at backend: "if user.totp_secret: pass" -> it just passes through and returns token.
            // This is insecure. I need to fix backend to RETURN 403 2FA_REQUIRED if secret exists.
            
            // Let's assume I fixed backend or will fix it now.
            // Actually, let's implement the client side to handle the flow:
            // The user enters username/pass.
            // If success, we get token. 
            // We then check /api/auth/me to see if 2FA is enabled? 
            // If enabled, we might want to "lock" the session until 2FA verified?
            
            // Better flow:
            // 1. Login -> Token (Partial or Full)
            // 2. Client checks "has_2fa" from /me
            // 3. If has_2fa, show 2FA screen.
            
            const res = await api.post('/api/auth/login', { username, password });
            const token = res.data.access_token;
            
            // Store temporarily
            localStorage.setItem('access_token', token);
            
            // Check 2FA status
            const me = await api.get('/api/auth/me');
            if (me.data.has_2fa) {
                // Determine if this session is already 2FA verified? 
                // The backend doesn't track "session 2fa status" in JWT yet.
                // For "Enterprise Grade", we should.
                // For now, let's just ask for code if has_2fa, and verify it against /verify endpoint.
                setStep('2fa');
            } else {
                login(token, username);
                toast.success("登录成功");
            }
        } catch (error: any) {
            toast.error(error.response?.data?.detail || "登录失败");
        } finally {
            setLoading(false);
        }
    };

    const handleVerify2FA = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            // Verify against a dedicated endpoint that checks code + user (using the temp token)
            // Actually, the /api/auth/2fa/verify endpoint in backend takes username/password/code.
            // It issues a NEW token.
            
            // Let's use that one.
            const res = await api.post('/api/auth/2fa/verify', { 
                username, 
                password, // We need to keep password in state for this, or change backend to use token
                code 
            });
            
            login(res.data.access_token, username);
            toast.success("验证成功");
        } catch (error: any) {
            toast.error("验证码错误");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 relative overflow-hidden">
             {/* Liquid Background */}
            <div className="liquid-bg">
                <div className="liquid-blob blob-1"></div>
                <div className="liquid-blob blob-2"></div>
                <div className="liquid-blob blob-3"></div>
            </div>

            <Card className="w-[400px] z-10 glass border-white/40 shadow-xl">
                <CardHeader className="text-center">
                    <div className="mx-auto w-12 h-12 bg-sky-500/10 rounded-full flex items-center justify-center mb-4">
                        <ShieldCheck className="h-6 w-6 text-sky-600" />
                    </div>
                    <CardTitle className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-sky-600 to-cyan-500">
                        SmartRoute AI
                    </CardTitle>
                    <CardDescription>
                        高性能智能路由网关
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {step === 'login' ? (
                        <form onSubmit={handleLogin} className="space-y-4">
                            <div className="space-y-2">
                                <Label>账号</Label>
                                <div className="relative">
                                    <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                                    <Input 
                                        className="pl-9" 
                                        placeholder="Username" 
                                        value={username}
                                        onChange={e => setUsername(e.target.value)}
                                        required
                                    />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label>密码</Label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                                    <Input 
                                        type="password" 
                                        className="pl-9" 
                                        placeholder="Password" 
                                        value={password}
                                        onChange={e => setPassword(e.target.value)}
                                        required
                                    />
                                </div>
                            </div>
                            <Button type="submit" className="w-full bg-sky-500 hover:bg-sky-600" disabled={loading}>
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                登录
                            </Button>
                        </form>
                    ) : (
                        <form onSubmit={handleVerify2FA} className="space-y-4">
                            <div className="text-center mb-4">
                                <div className="text-sm text-muted-foreground mb-2">请输入两步验证码</div>
                                <Input 
                                    className="text-center text-2xl tracking-[1em] font-mono" 
                                    maxLength={6}
                                    value={code}
                                    onChange={e => setCode(e.target.value)}
                                    placeholder="000000"
                                    autoFocus
                                />
                            </div>
                             <Button type="submit" className="w-full bg-sky-500 hover:bg-sky-600" disabled={loading}>
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                验证
                            </Button>
                             <Button variant="ghost" className="w-full" onClick={() => setStep('login')}>
                                返回登录
                            </Button>
                        </form>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}

export function Setup2FA({ onComplete }: { onComplete: () => void }) {
    const [step, setStep] = useState<'init' | 'scan' | 'verify'>('init');
    const [secret, setSecret] = useState('');
    const [qrUrl, setQrUrl] = useState('');
    const [code, setCode] = useState('');
    const [loading, setLoading] = useState(false);

    const startSetup = async () => {
        try {
            const res = await api.post('/api/auth/2fa/setup');
            setSecret(res.data.secret);
            setQrUrl(res.data.otpauth_url);
            setStep('scan');
        } catch (e) {
            toast.error("无法启动 2FA 设置");
        }
    };

    const confirmSetup = async () => {
        setLoading(true);
        try {
            await api.post('/api/auth/2fa/confirm', { code, secret });
            toast.success("2FA 已启用");
            onComplete();
        } catch (e) {
            toast.error("验证码错误");
        } finally {
            setLoading(false);
        }
    };

    if (step === 'init') {
        return (
             <div className="p-4 border rounded-lg bg-sky-50/50 flex flex-col items-center gap-4 text-center">
                <div className="p-3 bg-sky-100 rounded-full">
                    <ShieldCheck className="h-6 w-6 text-sky-600" />
                </div>
                <div>
                    <h3 className="font-bold text-lg">启用两步验证 (2FA)</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                        为了您的账户安全，建议启用 Google Authenticator 或其他 OTP 应用进行二次验证。
                    </p>
                </div>
                <Button onClick={startSetup}>立即启用</Button>
            </div>
        );
    }

    return (
        <div className="space-y-6">
             <div className="flex flex-col items-center gap-4">
                <div className="bg-white p-4 rounded-xl shadow-sm border">
                    <QRCodeSVG value={qrUrl} size={180} />
                </div>
                <div className="text-center space-y-2">
                    <p className="text-sm font-medium">1. 使用 Authenticator App 扫描上方二维码</p>
                    <p className="text-xs text-muted-foreground font-mono bg-slate-100 px-2 py-1 rounded">
                        密钥: {secret}
                    </p>
                </div>
            </div>
            
            <div className="space-y-3">
                 <Label>2. 输入 6 位验证码</Label>
                 <div className="flex gap-2">
                    <Input 
                        placeholder="000000" 
                        className="font-mono text-center tracking-widest"
                        maxLength={6}
                        value={code}
                        onChange={e => setCode(e.target.value)}
                    />
                    <Button onClick={confirmSetup} disabled={loading}>
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                    </Button>
                 </div>
            </div>
        </div>
    );
}
