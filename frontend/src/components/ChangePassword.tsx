import { useState } from 'react';
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export function ChangePassword() {
    const [oldPassword, setOldPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (newPassword !== confirmPassword) {
            toast.error("新密码两次输入不一致");
            return;
        }
        
        setLoading(true);
        try {
            await api.post('/api/auth/change-password', { 
                old_password: oldPassword,
                new_password: newPassword 
            });
            toast.success("密码修改成功");
            setOldPassword('');
            setNewPassword('');
            setConfirmPassword('');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || "密码修改失败");
        } finally {
            setLoading(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4 max-w-sm">
            <div className="space-y-2">
                <Label>当前密码</Label>
                <Input 
                    type="password"
                    value={oldPassword}
                    onChange={e => setOldPassword(e.target.value)}
                    required
                />
            </div>
            <div className="space-y-2">
                <Label>新密码</Label>
                <Input 
                    type="password"
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    required
                    minLength={6}
                />
            </div>
            <div className="space-y-2">
                <Label>确认新密码</Label>
                <Input 
                    type="password"
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    required
                    minLength={6}
                />
            </div>
            <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                修改密码
            </Button>
        </form>
    );
}
