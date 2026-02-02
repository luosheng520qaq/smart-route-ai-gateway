import { useState } from 'react';
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';

export function ChangeUsername() {
    const [newUsername, setNewUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const { login } = useAuth();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        
        setLoading(true);
        try {
            const response = await api.post('/api/auth/change-username', { 
                new_username: newUsername,
                password: password 
            });
            
            // Update auth state with new token and username
            if (response.data.access_token && response.data.username) {
                 login(response.data.access_token, response.data.username);
            }

            toast.success("用户名修改成功");
            setNewUsername('');
            setPassword('');
            
        } catch (error: any) {
            toast.error(error.response?.data?.detail || "用户名修改失败");
        } finally {
            setLoading(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4 max-w-sm">
            <div className="space-y-2">
                <Label>新用户名</Label>
                <Input 
                    type="text"
                    value={newUsername}
                    onChange={e => setNewUsername(e.target.value)}
                    required
                    minLength={3}
                    placeholder="输入新用户名"
                />
            </div>
            <div className="space-y-2">
                <Label>当前密码</Label>
                <Input 
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    placeholder="验证当前密码"
                />
            </div>
            <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                确认修改
            </Button>
        </form>
    );
}
