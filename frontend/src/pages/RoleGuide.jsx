import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
    ArrowRight,
    Calculator,
    CheckCircle2,
    Cpu,
    Factory,
    HardHat,
    Lock,
    Network,
    Play,
    Ruler,
    Shield,
    Sparkles,
    Wrench,
    X,
    Zap,
} from "lucide-react";
import { api, errMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";

const ROLES = [
    { id: "detailer", label: "Detailer", icon: Ruler, tag: "Shop drawings · BOMs · models" },
    { id: "engineer", label: "Engineer", icon: HardHat, tag: "Connection design · clash · code" },
    { id: "fabricator", label: "Fabricator", icon: Factory, tag: "Cut lists · NC files · procurement" },
    { id: "estimator", label: "Estimator", icon: Calculator, tag: "Pricing · margin · bid strategy" },
    { id: "pm", label: "Project Manager", icon: Wrench, tag: "Schedule · RFIs · change orders" },
    { id: "modular", label: "Modular", icon: Network, tag: "Pre-engineered kits · interfaces" },
];

const ROLE_COLORS = {
    detailer: "#f5a800",
    engineer: "#60a5fa",
    fabricator: "#f97316",
    estimator: "#16a34a",
    pm: "#a78bfa",
    modular: "#14b8a6",
};

export default function RoleGuide() {
    const { user } = useAuth();
    const [modes, setModes] = useState([]);
    const [activeRole, setActiveRole] = useState(user?.role === "admin" ? "detailer" : user?.role || "detailer");
    const [loading, setLoading] = useState(true);
    const [runningId, setRunningId] = useState(null);
    const [modalMode, setModalMode] = useState(null);
    const nav = useNavigate();

    useEffect(() => {
        (async () => {
            try {
                const { data } = await api.get("/api/analyses/modes");
                setModes(data.modes);
            } catch (e) {
                toast.error(errMessage(e));
            }
            setLoading(false);
        })();
    }, []);

    const isAdmin = user?.role === "admin";

    const byRole = useMemo(() => {
        if (!modes.length) return [];
        return modes.filter(
            (m) => m.roles?.includes(activeRole) || m.id === "CHAT_ASSISTANT",
        );
    }, [modes, activeRole]);

    const locked = useMemo(() => {
        if (!modes.length) return [];
        return modes.filter(
            (m) => !m.roles?.includes(activeRole) && m.id !== "CHAT_ASSISTANT",
        );
    }, [modes, activeRole]);

    const runDemo = async (mode) => {
        setRunningId(mode.id);
        try {
            const { data } = await api.post("/api/analyses/demo", { mode: mode.id });
            toast.success(`Running ${mode.label}… redirecting.`);
            setTimeout(() => nav(`/analyses/${data.id}`), 300);
        } catch (e) {
            toast.error(errMessage(e));
            setRunningId(null);
        }
    };

    return (
        <div className="min-h-full bg-background">
            {/* HERO */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="relative overflow-hidden border-b border-ink-line bg-navy px-10 py-14 text-white"
            >
                <div className="absolute inset-0 tech-grid opacity-40" />
                <div className="absolute -right-20 -top-10 h-64 w-64 rounded-full bg-gold/10 blur-3xl" />
                <div className="relative">
                    <div className="text-overline">Role Guide · Demo Console</div>
                    <h1 className="mt-3 font-heading text-4xl font-black leading-tight tracking-tight md:text-6xl">
                        Flex every mode.<br />
                        <span className="text-gold">Zero drawings required.</span>
                    </h1>
                    <p className="mt-4 max-w-2xl text-base text-white/70 md:text-lg">
                        Pick a role below, then fire a one-click live demo. STRUCTMIND CORE runs
                        against a representative mid-size steel project and delivers a full report
                        with all 5 export formats.
                        {isAdmin && (
                            <span className="ml-2 inline-flex items-center gap-1 border border-gold px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-gold">
                                <Zap size={10} />
                                Admin · bypass all role locks
                            </span>
                        )}
                    </p>
                </div>
            </motion.div>

            {/* ROLE TABS */}
            <div className="sticky top-0 z-30 border-b border-ink-line bg-white/90 backdrop-blur-xl">
                <div className="container-steel flex gap-2 overflow-x-auto py-4">
                    {ROLES.map((r, i) => {
                        const Icon = r.icon;
                        const active = activeRole === r.id;
                        return (
                            <motion.button
                                key={r.id}
                                onClick={() => setActiveRole(r.id)}
                                data-testid={`role-tab-${r.id}`}
                                whileHover={{ y: -2 }}
                                whileTap={{ scale: 0.98 }}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ duration: 0.3, delay: i * 0.04 }}
                                className={`group flex min-w-[180px] flex-shrink-0 flex-col border p-3 text-left transition-all ${
                                    active
                                        ? "border-navy bg-navy text-white"
                                        : "border-ink-line bg-white text-ink hover:border-navy"
                                }`}
                            >
                                <div className="flex items-center gap-2">
                                    <Icon size={14} className={active ? "text-gold" : "text-navy"} />
                                    <span className="font-heading text-sm font-bold uppercase tracking-wide">
                                        {r.label}
                                    </span>
                                </div>
                                <div
                                    className={`mt-1 font-mono text-[10px] uppercase tracking-wider ${
                                        active ? "text-white/60" : "text-ink-muted"
                                    }`}
                                >
                                    {r.tag}
                                </div>
                            </motion.button>
                        );
                    })}
                </div>
            </div>

            {/* CONTENT */}
            <div className="container-steel py-10">
                {loading ? (
                    <div className="grid gap-4 md:grid-cols-3">
                        {Array.from({ length: 9 }).map((_, i) => (
                            <Skeleton key={i} className="h-44 rounded-none" />
                        ))}
                    </div>
                ) : (
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={activeRole}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            transition={{ duration: 0.4 }}
                        >
                            {/* Stats header */}
                            <div
                                className="mb-8 flex items-center justify-between border-b border-ink-line pb-4"
                                style={{ borderBottomColor: ROLE_COLORS[activeRole] }}
                            >
                                <div>
                                    <div className="text-overline">Available modes</div>
                                    <div className="mt-1 font-heading text-3xl font-bold text-navy">
                                        {byRole.length} active ·{" "}
                                        <span className="text-ink-muted">
                                            {locked.length} role-locked
                                        </span>
                                    </div>
                                </div>
                                <div
                                    className="hidden h-16 w-16 items-center justify-center md:flex"
                                    style={{ background: ROLE_COLORS[activeRole] }}
                                >
                                    <Sparkles size={28} className="text-white" strokeWidth={1.5} />
                                </div>
                            </div>

                            {/* Available modes */}
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {byRole.map((m, i) => (
                                    <motion.div
                                        key={m.id}
                                        layout
                                        initial={{ opacity: 0, y: 16 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ duration: 0.35, delay: Math.min(i * 0.03, 0.3) }}
                                        whileHover={{ y: -4 }}
                                        data-testid={`role-mode-${m.id}`}
                                        className="card-steel group relative flex flex-col p-5 hover-lift"
                                    >
                                        <div className="absolute left-0 top-0 h-1 w-full bg-gold" />
                                        <div className="flex items-start justify-between">
                                            <div>
                                                <div className="font-mono text-[9px] uppercase tracking-wider text-gold">
                                                    {m.group}
                                                </div>
                                                <div className="mt-1 font-heading text-lg font-bold uppercase tracking-tight text-navy">
                                                    {m.label}
                                                </div>
                                            </div>
                                            {m.pro && (
                                                <span className="border border-navy bg-navy px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase text-gold">
                                                    PRO
                                                </span>
                                            )}
                                        </div>
                                        <p className="mt-3 line-clamp-3 text-sm text-ink-muted">
                                            {m.description}
                                        </p>
                                        <div className="mt-auto flex items-center justify-between border-t border-ink-line pt-3">
                                            <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                                {m.time}
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => setModalMode(m)}
                                                    data-testid={`preview-${m.id}`}
                                                    className="inline-flex items-center gap-1 border border-ink-line bg-white px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-navy hover:border-navy"
                                                >
                                                    Preview
                                                </button>
                                                <motion.button
                                                    whileHover={{ scale: 1.03 }}
                                                    whileTap={{ scale: 0.97 }}
                                                    onClick={() => runDemo(m)}
                                                    disabled={runningId === m.id}
                                                    data-testid={`run-demo-${m.id}`}
                                                    className="inline-flex items-center gap-1 bg-gold px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-navy hover:bg-gold-light"
                                                >
                                                    {runningId === m.id ? (
                                                        <>Running…</>
                                                    ) : (
                                                        <>
                                                            <Play size={10} fill="currentColor" />
                                                            Demo
                                                        </>
                                                    )}
                                                </motion.button>
                                            </div>
                                        </div>
                                    </motion.div>
                                ))}
                            </div>

                            {/* Locked modes */}
                            {locked.length > 0 && (
                                <>
                                    <div className="mt-12 mb-5 flex items-center gap-3">
                                        <div className="h-px flex-1 bg-ink-line" />
                                        <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
                                            <Lock size={12} />
                                            {locked.length} modes role-locked for {ROLES.find((r) => r.id === activeRole)?.label}
                                        </div>
                                        <div className="h-px flex-1 bg-ink-line" />
                                    </div>
                                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                                        {locked.map((m, i) => (
                                            <motion.div
                                                key={m.id}
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                                transition={{ delay: Math.min(i * 0.02, 0.3) }}
                                                className="relative border border-dashed border-ink-line bg-background p-4 opacity-80"
                                            >
                                                <div className="flex items-center gap-2">
                                                    <Lock size={10} className="text-ink-muted" />
                                                    <div className="font-heading text-sm font-semibold uppercase tracking-tight text-navy">
                                                        {m.label}
                                                    </div>
                                                </div>
                                                <div className="mt-1 font-mono text-[9px] uppercase tracking-wider text-ink-muted">
                                                    {m.group}
                                                </div>
                                                <div className="mt-2 flex flex-wrap gap-1">
                                                    {m.roles?.slice(0, 3).map((r) => (
                                                        <span
                                                            key={r}
                                                            className="border border-ink-line bg-white px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-wider text-ink-muted"
                                                        >
                                                            {r}
                                                        </span>
                                                    ))}
                                                </div>
                                                {isAdmin && (
                                                    <button
                                                        onClick={() => runDemo(m)}
                                                        disabled={runningId === m.id}
                                                        data-testid={`admin-run-locked-${m.id}`}
                                                        className="mt-3 inline-flex w-full items-center justify-center gap-1 bg-navy px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-gold hover:bg-navy-mid"
                                                    >
                                                        {runningId === m.id ? "Running…" : (
                                                            <>
                                                                <Play size={9} fill="currentColor" />
                                                                Admin demo
                                                            </>
                                                        )}
                                                    </button>
                                                )}
                                            </motion.div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </motion.div>
                    </AnimatePresence>
                )}
            </div>

            {/* PREVIEW MODAL */}
            <AnimatePresence>
                {modalMode && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-50 flex items-center justify-center bg-navy/60 px-4"
                        onClick={() => setModalMode(null)}
                    >
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 20 }}
                            transition={{ duration: 0.25 }}
                            className="card-steel w-full max-w-2xl overflow-hidden"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex items-center justify-between border-b border-ink-line bg-navy px-5 py-3">
                                <div>
                                    <div className="font-mono text-[10px] uppercase tracking-wider text-gold">
                                        {modalMode.group} · {modalMode.time}
                                    </div>
                                    <div className="font-heading text-xl font-bold uppercase tracking-tight text-white">
                                        {modalMode.label}
                                    </div>
                                </div>
                                <button onClick={() => setModalMode(null)} className="text-white/70 hover:text-gold">
                                    <X size={18} />
                                </button>
                            </div>
                            <div className="space-y-4 p-6">
                                <p className="text-sm leading-relaxed text-ink">
                                    {modalMode.description}
                                </p>
                                <div>
                                    <div className="mb-2 text-overline">Demo scope</div>
                                    <div className="border border-ink-line bg-background p-4 font-mono text-xs leading-relaxed text-ink">
                                        {modalMode.demo_prompt}
                                    </div>
                                </div>
                                <div>
                                    <div className="mb-2 text-overline">Available to roles</div>
                                    <div className="flex flex-wrap gap-2">
                                        {modalMode.roles?.map((r) => (
                                            <span
                                                key={r}
                                                className="border border-ink-line bg-white px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-navy"
                                            >
                                                {r}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                            <div className="flex gap-2 border-t border-ink-line bg-background px-5 py-3">
                                <button
                                    onClick={() => setModalMode(null)}
                                    className="btn-ghost-navy flex-1"
                                >
                                    Close
                                </button>
                                <button
                                    onClick={() => {
                                        runDemo(modalMode);
                                        setModalMode(null);
                                    }}
                                    data-testid={`modal-run-${modalMode.id}`}
                                    className="btn-gold flex-1"
                                >
                                    <Play size={12} fill="currentColor" />
                                    Run this demo
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
