import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
    AlertOctagon,
    CheckCircle2,
    MessageSquareQuote,
    Users,
    Layers,
    Activity,
} from "lucide-react";
import { api, errMessage } from "@/lib/api";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

const ADMIN_TABS = [
    { to: "/admin/users", label: "Users" },
    { to: "/admin/audit-log", label: "Audit Log" },
];

function AdminLayout({ children }) {
    const loc = useLocation();
    return (
        <div className="min-h-full bg-background">
            <div className="border-b border-ink-line bg-white px-10 py-10">
                <div className="text-overline">Admin Console</div>
                <h1 className="mt-2 font-heading text-5xl font-black uppercase leading-none tracking-tight text-navy">
                    Platform control
                </h1>
                <div className="mt-6 flex gap-6 border-b border-ink-line">
                    {ADMIN_TABS.map((t) => {
                        const active = loc.pathname === t.to;
                        return (
                            <Link
                                key={t.to}
                                to={t.to}
                                data-testid={`admin-tab-${t.label.toLowerCase().replace(' ', '-')}`}
                                className={`border-b-2 pb-3 font-heading text-sm uppercase tracking-wider transition-colors ${
                                    active
                                        ? "border-gold text-navy"
                                        : "border-transparent text-ink-muted hover:text-navy"
                                }`}
                            >
                                {t.label}
                            </Link>
                        );
                    })}
                </div>
            </div>
            <div className="container-steel py-10">{children}</div>
        </div>
    );
}

export function AdminUsers() {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [analytics, setAnalytics] = useState(null);

    const load = async () => {
        try {
            const [u, a] = await Promise.all([
                api.get("/api/admin/users"),
                api.get("/api/admin/analytics"),
            ]);
            setUsers(u.data.items);
            setAnalytics(a.data);
        } catch (e) {
            toast.error(errMessage(e));
        }
        setLoading(false);
    };

    useEffect(() => {
        load();
    }, []);

    const setRole = async (uid, role) => {
        try {
            await api.put(`/api/admin/users/${uid}`, { role });
            toast.success("Role updated.");
            load();
        } catch (e) {
            toast.error(errMessage(e));
        }
    };

    const setTier = async (uid, tier) => {
        try {
            await api.put(`/api/admin/users/${uid}`, { subscription_tier: tier });
            toast.success("Tier updated.");
            load();
        } catch (e) {
            toast.error(errMessage(e));
        }
    };

    const toggleActive = async (uid, active) => {
        try {
            await api.put(`/api/admin/users/${uid}`, { is_active: active });
            toast.success(active ? "User enabled." : "User disabled.");
            load();
        } catch (e) {
            toast.error(errMessage(e));
        }
    };

    return (
        <AdminLayout>
            <div className="grid gap-6 md:grid-cols-4">
                <Kpi label="TOTAL USERS" value={analytics?.total_users || 0} icon={Users} />
                <Kpi label="ACTIVE USERS" value={analytics?.active_users || 0} icon={CheckCircle2} />
                <Kpi label="PROJECTS" value={analytics?.total_projects || 0} icon={Layers} />
                <Kpi label="ANALYSES" value={analytics?.total_analyses || 0} icon={Activity} />
            </div>

            <div className="mt-8 card-steel">
                <div className="flex items-center justify-between border-b border-ink-line px-6 py-4">
                    <div className="font-heading text-lg font-bold uppercase tracking-wide text-navy">
                        All users
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                        {users.length} total
                    </div>
                </div>
                {loading ? (
                    <Skeleton className="m-6 h-64 rounded-none" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-background">
                                <tr className="border-b border-ink-line">
                                    {["Name", "Email", "Role", "Tier", "Active", "Verified", "Created"].map((h) => (
                                        <th
                                            key={h}
                                            className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted"
                                        >
                                            {h}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {users.map((u) => (
                                    <tr
                                        key={u.id}
                                        data-testid={`admin-user-${u.id}`}
                                        className="border-b border-ink-line last:border-b-0"
                                    >
                                        <td className="px-4 py-3 font-heading text-sm font-semibold uppercase tracking-wide text-navy">
                                            {u.first_name} {u.last_name}
                                        </td>
                                        <td className="px-4 py-3 font-mono text-xs text-ink-muted">
                                            {u.email}
                                        </td>
                                        <td className="px-4 py-3">
                                            <Select
                                                value={u.role}
                                                onValueChange={(v) => setRole(u.id, v)}
                                            >
                                                <SelectTrigger className="h-9 w-36 rounded-none border-ink-line font-mono text-[11px] uppercase">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="rounded-none">
                                                    {["detailer", "engineer", "fabricator", "estimator", "pm", "modular", "admin"].map(
                                                        (r) => (
                                                            <SelectItem
                                                                key={r}
                                                                value={r}
                                                                className="rounded-none font-mono text-[11px] uppercase"
                                                            >
                                                                {r}
                                                            </SelectItem>
                                                        ),
                                                    )}
                                                </SelectContent>
                                            </Select>
                                        </td>
                                        <td className="px-4 py-3">
                                            <Select
                                                value={u.subscription_tier}
                                                onValueChange={(v) => setTier(u.id, v)}
                                            >
                                                <SelectTrigger className="h-9 w-32 rounded-none border-ink-line font-mono text-[11px] uppercase">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="rounded-none">
                                                    {["free", "starter", "pro", "enterprise"].map((t) => (
                                                        <SelectItem
                                                            key={t}
                                                            value={t}
                                                            className="rounded-none font-mono text-[11px] uppercase"
                                                        >
                                                            {t}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </td>
                                        <td className="px-4 py-3">
                                            <button
                                                onClick={() => toggleActive(u.id, !u.is_active)}
                                                data-testid={`toggle-active-${u.id}`}
                                                className={`inline-flex items-center gap-1 border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                                                    u.is_active
                                                        ? "border-success text-success"
                                                        : "border-destructive text-destructive"
                                                }`}
                                            >
                                                {u.is_active ? "Active" : "Disabled"}
                                            </button>
                                        </td>
                                        <td className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider">
                                            {u.is_verified ? (
                                                <span className="text-success">✓ Verified</span>
                                            ) : (
                                                <span className="text-warning">Pending</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                            {new Date(u.created_at).toLocaleDateString()}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </AdminLayout>
    );
}

export function AdminAuditLog() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                const { data } = await api.get("/api/admin/audit-log?limit=200");
                setItems(data.items);
            } catch (e) {
                toast.error(errMessage(e));
            }
            setLoading(false);
        })();
    }, []);

    return (
        <AdminLayout>
            <div className="card-steel">
                <div className="flex items-center justify-between border-b border-ink-line px-6 py-4">
                    <div className="font-heading text-lg font-bold uppercase tracking-wide text-navy">
                        Audit log
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                        {items.length} events
                    </div>
                </div>
                {loading ? (
                    <Skeleton className="m-6 h-64 rounded-none" />
                ) : items.length === 0 ? (
                    <div className="p-12 text-center text-sm text-ink-muted">
                        No audit events recorded yet.
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-background">
                                <tr className="border-b border-ink-line">
                                    {["Time", "User", "Action", "Resource", "IP"].map((h) => (
                                        <th
                                            key={h}
                                            className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted"
                                        >
                                            {h}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {items.map((a) => (
                                    <tr
                                        key={a.id}
                                        className="border-b border-ink-line last:border-b-0"
                                    >
                                        <td className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                            {new Date(a.timestamp).toLocaleString()}
                                        </td>
                                        <td className="px-4 py-3 font-mono text-[10px] text-navy">
                                            {a.user_id.slice(0, 12)}…
                                        </td>
                                        <td className="px-4 py-3 font-heading text-sm font-semibold uppercase tracking-wide text-navy">
                                            {a.action}
                                        </td>
                                        <td className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                            {a.resource}
                                        </td>
                                        <td className="px-4 py-3 font-mono text-[10px] text-ink-muted">
                                            {a.ip_address || "—"}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </AdminLayout>
    );
}

function Kpi({ label, value, icon: Icon }) {
    return (
        <div className="card-steel flex items-center justify-between p-5">
            <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                    {label}
                </div>
                <div className="mt-2 font-heading text-4xl font-black leading-none text-navy">
                    {value}
                </div>
            </div>
            <Icon size={20} className="text-gold" />
        </div>
    );
}
