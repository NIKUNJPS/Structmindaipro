import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";
import { api } from "@/lib/api";
import { tokenStore } from "@/lib/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(() => tokenStore.getUser());
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const bootstrap = async () => {
            const token = tokenStore.getAccess();
            if (!token) {
                setLoading(false);
                return;
            }
            try {
                const { data } = await api.get("/api/auth/me");
                setUser(data);
                tokenStore.setUser(data);
            } catch {
                tokenStore.clear();
                setUser(null);
            } finally {
                setLoading(false);
            }
        };
        bootstrap();
    }, []);

    const login = useCallback((tokens, u) => {
        tokenStore.setTokens(tokens.access_token, tokens.refresh_token);
        tokenStore.setUser(u);
        setUser(u);
    }, []);

    const logout = useCallback(async () => {
        try {
            await api.post("/api/auth/logout");
        } catch {}
        tokenStore.clear();
        setUser(null);
    }, []);

    const refreshUser = useCallback(async () => {
        try {
            const { data } = await api.get("/api/auth/me");
            setUser(data);
            tokenStore.setUser(data);
        } catch {}
    }, []);

    const value = useMemo(
        () => ({ user, loading, login, logout, refreshUser, setUser }),
        [user, loading, login, logout, refreshUser],
    );
    return (
        <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
