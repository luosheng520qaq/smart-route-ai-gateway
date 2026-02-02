import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from './api';

interface AuthState {
    token: string | null;
    username: string | null;
    isAuthenticated: boolean;
    has2FA: boolean;
}

interface AuthContextType extends AuthState {
    login: (token: string, username: string) => void;
    logout: () => void;
    checkAuth: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [state, setState] = useState<AuthState>({
        token: localStorage.getItem('access_token'),
        username: localStorage.getItem('username'),
        isAuthenticated: !!localStorage.getItem('access_token'),
        has2FA: false
    });

    const login = (token: string, username: string) => {
        localStorage.setItem('access_token', token);
        localStorage.setItem('username', username);
        setState({
            token,
            username,
            isAuthenticated: true,
            has2FA: false // Will update on profile fetch
        });
    };

    const logout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        setState({
            token: null,
            username: null,
            isAuthenticated: false,
            has2FA: false
        });
    };

    const checkAuth = async () => {
        if (!state.token) return false;
        try {
            const res = await api.get('/api/auth/me');
            setState(prev => ({ 
                ...prev, 
                isAuthenticated: true,
                has2FA: res.data.has_2fa 
            }));
            return true;
        } catch (e) {
            logout();
            return false;
        }
    };

    // Check auth on mount
    useEffect(() => {
        checkAuth();
    }, []);

    return (
        <AuthContext.Provider value={{ ...state, login, logout, checkAuth }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
